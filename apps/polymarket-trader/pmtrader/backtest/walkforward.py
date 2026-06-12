"""Walk-forward backtest gate: the primary, reboot-proof evidence of edge.

Splits stored price history into K equal-duration time folds, replays FRESH
strategy instances over each fold independently, and passes a strategy only
if (a) pooled per-trade P&L has a bootstrap 95% CI lower bound > 0, (b) at
least `min_active_folds` folds traded, and (c) every fold with at least
`min_fold_trades` trades has positive mean P&L. No fold sees another fold's
ticks; settlement uses each market's real resolution (the realized outcome
of a position entered inside the fold, not lookahead for entry decisions).

Honesty limits inherited from the replay engine: sampled mids, synthetic
finite-depth books, pessimistic costs. S2 (microstructure) cannot be judged
here. S4's whitelist was itself derived from this dataset — its headline
evidence is run_calibration_research's internal walk-forward; this harness
re-checks it at execution level only.
"""
from __future__ import annotations

import time
from typing import Callable

from pmtrader.backtest.costs import CostModel
from pmtrader.backtest.replay import ReplayEngine
from pmtrader.backtest.stats import bootstrap_ci
from pmtrader.datalayer.store import Store
from pmtrader.strategies.base import Strategy

MIN_POOLED_TRADES = 30
MIN_FOLD_TRADES = 5
MIN_ACTIVE_FOLDS = 2


def run_walkforward(store: Store,
                    strategy_factory: Callable[[], list[Strategy]],
                    k: int = 4, cost: CostModel | None = None,
                    starting_cash: float = 1000.0,
                    min_pooled_trades: int = MIN_POOLED_TRADES,
                    min_fold_trades: int = MIN_FOLD_TRADES,
                    min_active_folds: int = MIN_ACTIVE_FOLDS) -> dict:
    cost = cost or CostModel()
    lo_ts, hi_ts = store.price_history_span()
    if lo_ts is None or hi_ts is None or hi_ts <= lo_ts:
        return {"error": "no price history in store", "strategies": {}}

    edges = [lo_ts + (hi_ts - lo_ts) * i / k for i in range(k + 1)]
    edges[-1] += 1.0  # inclusive final tick
    acc: dict[str, dict] = {}

    def slot(name: str) -> dict:
        return acc.setdefault(name, {"fold_ns": [0] * k,
                                     "fold_means": [None] * k, "pnls": []})

    for i in range(k):
        strategies = strategy_factory()
        engine = ReplayEngine(store, strategies, cost,
                              start_ts=edges[i], end_ts=edges[i + 1],
                              starting_cash=starting_cash)
        result = engine.run()
        for s in strategies:
            slot(s.name)
        for name, pnls in result.per_strategy_pnl().items():
            d = slot(name)
            d["fold_ns"][i] = len(pnls)
            d["fold_means"][i] = sum(pnls) / len(pnls) if pnls else None
            d["pnls"].extend(pnls)

    out = {"generated_ts": time.time(), "k": k,
           "cost": {"half_spread": cost.half_spread,
                    "slippage_bps": cost.slippage_bps,
                    "book_depth": cost.book_depth},
           "strategies": {}}
    for name, d in acc.items():
        pnls = d["pnls"]
        lo, hi = bootstrap_ci(pnls)
        active = [m for n, m in zip(d["fold_ns"], d["fold_means"])
                  if n >= min_fold_trades and m is not None]
        passed = (len(pnls) >= min_pooled_trades and lo > 0
                  and len(active) >= min_active_folds
                  and all(m > 0 for m in active))
        out["strategies"][name] = {
            "n_trades": len(pnls),
            "mean_pnl": sum(pnls) / len(pnls) if pnls else 0.0,
            "pooled_ci": [lo, hi],
            "fold_ns": d["fold_ns"],
            "fold_means": [None if m is None else round(m, 6)
                           for m in d["fold_means"]],
            "pass": passed,
        }
    return out
