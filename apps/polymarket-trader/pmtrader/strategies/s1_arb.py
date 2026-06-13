"""S1 — structural arbitrage scanner.

Two riskless-class structures:
1. Binary pair: ask(YES) + ask(NO) < 1 - fees - epsilon  -> buy both legs,
   each pair pays exactly $1 at resolution regardless of outcome.
2. Neg-risk set: sum of YES asks across all mutually exclusive outcomes of an
   event < 1 - fees - epsilon -> buy every YES; exactly one pays $1.

Legging risk is bounded by emitting all legs atomically under one group_id;
the execution router unwinds the filled side if a leg fails. One live arb per
market/event at a time; released when the market resolves or legs unwind.
"""
from __future__ import annotations

import itertools

from pmtrader.core.fees import taker_fee_per_share
from pmtrader.core.models import Intent, Market, OrderBook, Side
from pmtrader.strategies.base import Strategy, StrategyContext

_group_counter = itertools.count(1)


class S1Arb(Strategy):
    name = "s1_arb"
    DEFAULTS = {
        "epsilon": 0.005,        # minimum net edge per $1 pair after fees
        "max_book_frac": 1.0,    # fraction of displayed depth we may take
        "max_pairs_per_trade": 5000.0,
    }
    PARAM_BOUNDS = {
        "epsilon": (0.001, 0.05),
        "max_book_frac": (0.05, 1.0),
        "max_pairs_per_trade": (10.0, 100_000.0),
    }

    def __init__(self, params: dict | None = None):
        super().__init__(params)
        self.pending: set[str] = set()  # condition_ids / event ids with live arbs

    # -- helpers ---------------------------------------------------------------
    def _leg_fee(self, market: Market, price: float) -> float:
        return taker_fee_per_share(price, schedule=market.fee_schedule,
                                   fees_enabled=market.fees_enabled)

    def _build_legs(self, legs: list[tuple[Market, str, float, float]],
                    payout: float, budget: float, key: str,
                    reasoning: str) -> list[Intent]:
        """legs: (market, token_id, ask_price, ask_depth). payout: $ per set."""
        total_cost = sum(price for _, _, price, _ in legs)
        total_fees = sum(self._leg_fee(m, price) for m, _, price, _ in legs)
        edge = payout - total_cost - total_fees
        if edge < self.params["epsilon"]:
            return []
        depth_cap = min(depth * self.params["max_book_frac"] for _, _, _, depth in legs)
        budget_cap = budget / (total_cost + total_fees) if total_cost + total_fees > 0 else 0
        size = min(depth_cap, budget_cap, self.params["max_pairs_per_trade"])
        size = float(int(size))  # whole shares
        min_size = max(m.min_size for m, _, _, _ in legs)
        if size < min_size:
            return []
        group = f"s1-{next(_group_counter)}"
        text = (f"{reasoning} cost={total_cost:.4f} fees={total_fees:.4f} "
                f"edge={edge:.4f}/share x {size:.0f}")
        intents = [
            Intent(strategy=self.name, token_id=token_id, side=Side.BUY,
                   price=price, size=size, expected_edge=edge / len(legs),
                   reasoning=text, group_id=group, condition_id=m.condition_id,
                   event_id=m.event_id)
            for m, token_id, price, _ in legs
        ]
        self.pending.add(key)
        return intents

    # -- binary pair -------------------------------------------------------------
    def on_books(self, market: Market, books: dict[str, OrderBook],
                 ctx: StrategyContext) -> list[Intent]:
        if market.condition_id in self.pending:
            return []
        yes = books.get(market.token_id_yes)
        no = books.get(market.token_id_no)
        if yes is None or no is None or yes.best_ask is None or no.best_ask is None:
            return []
        pair_sum = yes.best_ask + no.best_ask
        if pair_sum >= 1.0:
            return []
        return self._build_legs(
            legs=[(market, market.token_id_yes, yes.best_ask, yes.best_ask_size),
                  (market, market.token_id_no, no.best_ask, no.best_ask_size)],
            payout=1.0, budget=ctx.budget, key=market.condition_id,
            reasoning=f"binary pair arb sum={pair_sum:.4f}")

    # -- neg-risk set --------------------------------------------------------------
    def on_event(self, event, books: dict[str, OrderBook],
                 ctx: StrategyContext) -> list[Intent]:
        if not event.neg_risk or not event.markets:
            return []
        key = f"ev:{event.id}"
        if key in self.pending:
            return []
        legs = []
        for m in event.markets:
            book = books.get(m.token_id_yes)
            if book is None or book.best_ask is None:
                return []  # need every outcome priced to lock the set
            legs.append((m, m.token_id_yes, book.best_ask, book.best_ask_size))
        yes_sum = sum(price for _, _, price, _ in legs)
        if yes_sum >= 1.0:
            return []
        return self._build_legs(legs, payout=1.0, budget=ctx.budget, key=key,
                                reasoning=f"neg-risk set arb n={len(legs)} "
                                          f"sum={yes_sum:.4f}")

    # -- lifecycle ------------------------------------------------------------------
    def on_market_resolved(self, condition_id: str) -> None:
        self.pending.discard(condition_id)

    def on_group_unwound(self, key: str) -> None:
        self.pending.discard(key)
