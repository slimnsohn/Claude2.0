"""Risk manager — the gate every intent passes through. No exceptions.

Pure function over a PortfolioSnapshot: no I/O, fully unit-testable.
Returns Approved (possibly downsized by fractional Kelly) or Veto(rule, detail).
This is a money path: 100% branch coverage required.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from pmtrader.core.fees import taker_fee_per_share
from pmtrader.core.models import Intent, Market, OrderBook, Position, Side
from pmtrader.strategies.s4_calib import parse_end_date

DEFAULT_RULES = dict(
    max_market_frac=0.05,       # max exposure per market, fraction of equity
    max_event_frac=0.10,        # max exposure per correlated event
    max_at_risk_frac=0.80,      # max total capital at risk
    daily_loss_halt_frac=0.10,  # daily realized+unrealized loss -> halt
    max_book_frac=0.25,         # max order size vs displayed depth at level
    stale_book_sec=10.0,        # book older than this -> no new orders
    kelly_fraction=0.25,        # quarter-Kelly
    resolution_blackout_min=10.0,
)

UNWIND_EXEMPT_STRATEGIES = {"s1_arb"}  # may exit (reduce) during blackout


@dataclass
class PortfolioSnapshot:
    now: float
    cash: float
    equity: float
    day_pnl: float
    positions: dict[str, Position]
    marks: dict[str, float]
    books: dict[str, OrderBook]
    markets: dict[str, Market]
    halted: bool = False


@dataclass
class Approved:
    size: float
    detail: str


@dataclass
class Veto:
    rule: str
    detail: str


@dataclass
class RiskManager:
    rules: dict = field(default_factory=lambda: dict(DEFAULT_RULES))

    def check(self, intent: Intent, snap: PortfolioSnapshot) -> Approved | Veto:
        r = self.rules

        if snap.halted:
            return Veto("halted", "trading halted")

        if snap.day_pnl <= -r["daily_loss_halt_frac"] * snap.equity:
            return Veto("daily_loss_halt",
                        f"day pnl {snap.day_pnl:.2f} <= "
                        f"-{r['daily_loss_halt_frac']:.0%} of equity {snap.equity:.2f}")

        book = snap.books.get(intent.token_id)
        if book is None or snap.now - book.ts > r["stale_book_sec"]:
            age = "missing" if book is None else f"{snap.now - book.ts:.1f}s old"
            return Veto("stale_book", f"book {age}")

        market = snap.markets.get(intent.condition_id or "")
        held = snap.positions.get(intent.token_id)
        held_size = held.size if held else 0.0
        is_reduce = intent.side == Side.SELL and held_size > 0

        if intent.side == Side.SELL and intent.size > held_size + 1e-9:
            return Veto("short_sale",
                        f"sell {intent.size} > held {held_size}")

        # resolution blackout (exits by exempt strategies allowed)
        if market is not None:
            end_ts = parse_end_date(market.end_date)
            if end_ts is not None and \
                    end_ts - snap.now <= r["resolution_blackout_min"] * 60:
                if not (is_reduce and intent.strategy in UNWIND_EXEMPT_STRATEGIES):
                    return Veto("resolution_blackout",
                                f"{(end_ts - snap.now) / 60:.1f} min to resolution")

        # fee-adjusted EV (makers pay no taker fee)
        if not is_reduce:
            fee = 0.0
            if not intent.post_only and market is not None:
                fee = taker_fee_per_share(intent.price,
                                          schedule=market.fee_schedule,
                                          fees_enabled=market.fees_enabled)
            if intent.expected_edge - fee <= 0:
                return Veto("ev_after_fees",
                            f"edge {intent.expected_edge:.4f} - fee {fee:.4f} <= 0")

        # depth: marketable orders may consume at most max_book_frac of the
        # displayed liquidity they would take. Resting orders add liquidity.
        marketable = (intent.side == Side.BUY and book.best_ask is not None
                      and intent.price >= book.best_ask) or \
                     (intent.side == Side.SELL and book.best_bid is not None
                      and intent.price <= book.best_bid)
        if marketable and not intent.post_only:
            depth = (book.ask_depth_at_or_below(intent.price)
                     if intent.side == Side.BUY
                     else book.bid_depth_at_or_above(intent.price))
            if intent.size > r["max_book_frac"] * depth:
                return Veto("max_book_frac",
                            f"size {intent.size} > {r['max_book_frac']:.0%} "
                            f"of depth {depth}")

        size = intent.size
        if not is_reduce:
            # exposure caps (notional at intent price)
            new_notional = size * intent.price
            market_exposure = self._exposure(
                snap, lambda p: p.condition_id == intent.condition_id)
            if market_exposure + new_notional > r["max_market_frac"] * snap.equity:
                return Veto("max_market_frac",
                            f"market exposure {market_exposure + new_notional:.2f} "
                            f"> {r['max_market_frac']:.0%} of {snap.equity:.2f}")

            if intent.event_id:
                event_exposure = self._exposure(
                    snap, lambda p: p.event_id == intent.event_id)
                if event_exposure + new_notional > r["max_event_frac"] * snap.equity:
                    return Veto("max_event_frac",
                                f"event exposure {event_exposure + new_notional:.2f} "
                                f"> {r['max_event_frac']:.0%} of {snap.equity:.2f}")

            total_at_risk = self._exposure(snap, lambda p: True)
            if total_at_risk + new_notional > r["max_at_risk_frac"] * snap.equity:
                return Veto("max_at_risk_frac",
                            f"at risk {total_at_risk + new_notional:.2f} "
                            f"> {r['max_at_risk_frac']:.0%} of {snap.equity:.2f}")

            # fractional Kelly cap on entries: f* = edge / (p(1-p))
            variance = max(1e-6, intent.price * (1 - intent.price))
            kelly_dollars = (intent.expected_edge / variance) * snap.equity \
                * r["kelly_fraction"]
            kelly_shares = max(0.0, kelly_dollars / intent.price)
            size = min(size, kelly_shares)
            if size < 1.0:
                return Veto("kelly_zero",
                            f"kelly cap {kelly_shares:.2f} shares < 1")

        return Approved(size=size,
                        detail=f"approved size={size:.0f} "
                               f"(requested {intent.size:.0f})")

    @staticmethod
    def _exposure(snap: PortfolioSnapshot, predicate) -> float:
        total = 0.0
        for token_id, pos in snap.positions.items():
            if pos.size > 0 and predicate(pos):
                mark = snap.marks.get(token_id, pos.avg_cost)
                total += pos.size * mark
        return total
