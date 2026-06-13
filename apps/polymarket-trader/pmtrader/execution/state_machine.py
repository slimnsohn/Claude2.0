"""Order lifecycle state machine with explicit transition table and audit trail.

This is a money path: 100% branch coverage required. Every transition is
recorded as (ts, from, to, why). Reconciliation resolves divergence between
local state and exchange state after reconnects.
"""
from __future__ import annotations

from pmtrader.core.models import Intent, OrderStatus

LEGAL: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.CREATED: {OrderStatus.SUBMITTED, OrderStatus.REJECTED},
    OrderStatus.SUBMITTED: {OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED,
                            OrderStatus.FILLED, OrderStatus.REJECTED,
                            OrderStatus.CANCELLED, OrderStatus.EXPIRED},
    OrderStatus.OPEN: {OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED,
                       OrderStatus.CANCELLED, OrderStatus.EXPIRED},
    OrderStatus.PARTIALLY_FILLED: {OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED,
                                   OrderStatus.CANCELLED, OrderStatus.EXPIRED},
    OrderStatus.FILLED: set(),
    OrderStatus.CANCELLED: set(),
    OrderStatus.REJECTED: set(),
    OrderStatus.EXPIRED: set(),
}
TERMINAL = {s for s, targets in LEGAL.items() if not targets}
_FILLABLE = {OrderStatus.SUBMITTED, OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED}


class InvalidTransition(Exception):
    pass


class OrderRecord:
    def __init__(self, order_id: str, intent: Intent, ts: float,
                 exchange_id: str | None = None):
        self.order_id = order_id
        self.intent = intent
        self.exchange_id = exchange_id
        self.status = OrderStatus.CREATED
        self.filled_size = 0.0
        self.avg_fill_price = 0.0
        self.created_ts = ts
        self.updated_ts = ts
        self.orphaned = False
        self.audit: list[tuple[float, OrderStatus, OrderStatus, str]] = []

    @property
    def remaining(self) -> float:
        return self.intent.size - self.filled_size

    def transition(self, to: OrderStatus, ts: float, why: str) -> None:
        if to not in LEGAL[self.status]:
            raise InvalidTransition(f"{self.order_id}: {self.status} -> {to} ({why})")
        self.audit.append((ts, self.status, to, why))
        self.status = to
        self.updated_ts = ts

    def apply_fill(self, size: float, price: float, ts: float) -> None:
        if self.status not in _FILLABLE:
            raise InvalidTransition(
                f"{self.order_id}: fill in state {self.status}")
        if size <= 0:
            raise ValueError(f"{self.order_id}: non-positive fill size {size}")
        if size > self.remaining + 1e-9:
            raise ValueError(
                f"{self.order_id}: overfill {size} > remaining {self.remaining}")
        total_cost = self.avg_fill_price * self.filled_size + price * size
        self.filled_size += size
        self.avg_fill_price = total_cost / self.filled_size
        done = self.remaining <= 1e-9
        self.transition(OrderStatus.FILLED if done else OrderStatus.PARTIALLY_FILLED,
                        ts, f"fill {size}@{price}")

    def reconcile(self, api_status: str, api_filled_size: float,
                  api_avg_price: float, ts: float) -> float:
        """Align local state with exchange truth. Returns the fill-size gap
        that was synthesized (0 if none)."""
        gap = 0.0
        if api_filled_size > self.filled_size + 1e-9:
            gap = api_filled_size - self.filled_size
            # back out the gap's average price from the API's overall average
            gap_price = api_avg_price
            if api_avg_price > 0 and self.filled_size > 0:
                gap_price = max(0.001, min(0.999, (
                    api_avg_price * api_filled_size
                    - self.avg_fill_price * self.filled_size) / gap))
            self.apply_fill(gap, gap_price if gap_price > 0 else self.intent.price, ts)

        if self.status in TERMINAL:
            return gap

        target = {
            "FILLED": OrderStatus.FILLED,
            "CANCELLED": OrderStatus.CANCELLED,
            "EXPIRED": OrderStatus.EXPIRED,
            "REJECTED": OrderStatus.REJECTED,
            "OPEN": None,  # agreement
            "PARTIALLY_FILLED": None,
        }.get(api_status, "ORPHAN")

        if target == "ORPHAN":
            self.orphaned = True
            self.transition(OrderStatus.EXPIRED, ts,
                            f"reconcile: unknown api status {api_status!r}")
        elif target is not None and target != self.status:
            self.transition(target, ts, f"reconcile: api says {api_status}")
        return gap
