"""Execution router: one entry point for all order flow.

- Holds the active backend (paper or live — same interface).
- Enforces atomic group semantics for multi-leg arbs: if any leg of a group
  is rejected, all sibling working orders are cancelled and any filled size
  is unwound with marketable sell intents (handed to on_unwind for the
  normal strategy->risk->execution path, never bypassing risk).
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Callable, Optional

from pmtrader.core.models import Intent, OrderStatus, Side
from pmtrader.execution.state_machine import OrderRecord

log = logging.getLogger(__name__)


class ExecutionRouter:
    def __init__(self, backend, store,
                 on_unwind: Optional[Callable[[list[Intent]], None]] = None):
        self.backend = backend
        self.store = store
        self.on_unwind = on_unwind or (lambda intents: None)
        self.groups: dict[str, list[OrderRecord]] = defaultdict(list)
        self.dead_groups: set[str] = set()

    def submit(self, intent: Intent, now: float) -> OrderRecord:
        if intent.group_id and intent.group_id in self.dead_groups:
            rec = OrderRecord(order_id=f"dead-{intent.group_id}", intent=intent,
                              ts=now)
            rec.transition(OrderStatus.REJECTED, now, "group already failed")
            return rec
        rec = self.backend.submit(intent, now)
        if intent.group_id:
            self.groups[intent.group_id].append(rec)
            if rec.status == OrderStatus.REJECTED:
                self._fail_group(intent.group_id, now)
        return rec

    def cancel(self, order_id: str, now: float) -> None:
        self.backend.cancel(order_id, now)

    def cancel_all(self, now: float) -> None:
        self.backend.cancel_all(now)

    def _fail_group(self, group_id: str, now: float) -> None:
        self.dead_groups.add(group_id)
        unwind: list[Intent] = []
        for rec in self.groups[group_id]:
            if rec.status in (OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED):
                self.backend.cancel(rec.order_id, now)
            if rec.filled_size > 0:
                i = rec.intent
                unwind.append(Intent(
                    strategy=i.strategy,
                    token_id=i.token_id,
                    side=Side.SELL if i.side == Side.BUY else Side.BUY,
                    price=max(0.001, min(0.999, rec.avg_fill_price)),
                    size=rec.filled_size,
                    expected_edge=0.0,
                    reasoning=f"unwind failed group {group_id}: sibling leg rejected",
                    tif=i.tif,
                    condition_id=i.condition_id,
                    event_id=i.event_id))
        if unwind:
            log.warning("group %s failed; unwinding %d filled legs",
                        group_id, len(unwind))
        self.on_unwind(unwind)
