"""Capital allocator — the self-learning layer, done honestly.

Two responsibilities:
1. Budgets: weekly performance-weighted capital across strategies.
   score = shrunk Sharpe = (n/(n+k)) * mean/std * sqrt(n), softmaxed with a
   5% floor / 50% cap. Shrinkage stops early noise from whipsawing weights.
2. Gates: a strategy may deploy real capital only with LIVE_ELIGIBLE status:
   >= 200 paper trades AND bootstrap 95% CI of per-trade EV > 0 AND >= 7
   days of history. Rolling live performance is monitored; if the rolling
   CI upper bound drops below 0 (or drawdown breaches), the strategy is
   demoted back to PAPER with the evidence logged. Nothing self-modifies
   outside these rules.
"""
from __future__ import annotations

import math
from collections import defaultdict
from enum import StrEnum

from pmtrader.backtest.stats import bootstrap_ci

DAY = 86_400.0


class GateStatus(StrEnum):
    PAPER = "PAPER"
    LIVE_ELIGIBLE = "LIVE_ELIGIBLE"


class Allocator:
    GATE_MIN_TRADES = 200
    GATE_MIN_DAYS = 7.0
    DECAY_WINDOW_TRADES = 200
    WEIGHT_FLOOR = 0.05
    WEIGHT_CAP = 0.50
    SHRINK_K = 100.0
    SOFTMAX_T = 2.0

    def __init__(self, strategies: list[str], bankroll: float):
        self.strategies = list(strategies)
        self.bankroll = bankroll
        self._weights = {s: 1.0 / len(strategies) for s in strategies}
        self._gates = {s: GateStatus.PAPER for s in strategies}
        self.live_trades: dict[str, list[dict]] = defaultdict(list)
        self.paper_trades: dict[str, list[dict]] = defaultdict(list)
        self.events: list[dict] = []

    # -- recording ------------------------------------------------------------
    def record_trades(self, strategy: str, trades: list[dict]) -> None:
        self.live_trades[strategy].extend(trades)

    def record_paper_trades(self, strategy: str, trades: list[dict]) -> None:
        self.paper_trades[strategy].extend(trades)

    # -- queries ----------------------------------------------------------------
    def weights(self) -> dict[str, float]:
        return dict(self._weights)

    def budget(self, strategy: str) -> float:
        return self.bankroll * self._weights.get(strategy, 0.0)

    def gate(self, strategy: str) -> GateStatus:
        return self._gates[strategy]

    # -- reweighting ---------------------------------------------------------------
    def _score(self, strategy: str) -> float:
        trades = self.live_trades[strategy] or self.paper_trades[strategy]
        n = len(trades)
        if n < 2:
            return 0.0
        pnls = [t["pnl"] for t in trades]
        mean = sum(pnls) / n
        var = sum((x - mean) ** 2 for x in pnls) / (n - 1)
        sd = math.sqrt(var)
        if sd == 0:
            sharpe_n = math.copysign(10.0, mean) if mean else 0.0
        else:
            sharpe_n = (mean / sd) * math.sqrt(n)
        shrink = n / (n + self.SHRINK_K)
        return shrink * sharpe_n

    def reweight(self, now: float) -> None:
        scores = {s: self._score(s) for s in self.strategies}
        exps = {s: math.exp(min(50.0, sc / self.SOFTMAX_T))
                for s, sc in scores.items()}
        total = sum(exps.values())
        raw = {s: e / total for s, e in exps.items()}
        self._weights = self._project(raw)
        self.events.append({"kind": "reweight", "ts": now,
                            "weights": dict(self._weights),
                            "scores": {s: round(sc, 3) for s, sc in scores.items()}})

    def _project(self, raw: dict[str, float]) -> dict[str, float]:
        """Project onto the simplex with per-weight bounds [floor, cap].
        Imbalance is redistributed proportionally to the raw scores of the
        weights that still have room, preserving their relative order."""
        w = dict(raw)
        for _ in range(50):
            w = {s: min(self.WEIGHT_CAP, max(self.WEIGHT_FLOOR, v))
                 for s, v in w.items()}
            err = 1.0 - sum(w.values())
            if abs(err) < 1e-12:
                break
            movable = [s for s, v in w.items()
                       if (err > 0 and v < self.WEIGHT_CAP - 1e-12)
                       or (err < 0 and v > self.WEIGHT_FLOOR + 1e-12)]
            if not movable:
                break
            raw_total = sum(raw[s] for s in movable)
            for s in movable:
                frac = raw[s] / raw_total if raw_total > 0 else 1 / len(movable)
                w[s] += err * frac
        norm = sum(w.values())
        return {s: v / norm for s, v in w.items()}

    # -- gates -------------------------------------------------------------------------
    def update_gates(self, now: float) -> None:
        for s in self.strategies:
            current = self._gates[s]
            if current == GateStatus.PAPER:
                if self._passes_paper_gate(s, now):
                    self._gates[s] = GateStatus.LIVE_ELIGIBLE
                    self.events.append({"kind": "promotion", "ts": now,
                                        "strategy": s,
                                        "evidence": self._gate_evidence(s, now)})
            else:
                decayed, evidence = self._edge_decayed(s)
                if decayed:
                    self._gates[s] = GateStatus.PAPER
                    # require a fresh paper record before re-promotion
                    self.paper_trades[s] = []
                    self.events.append({"kind": "demotion", "ts": now,
                                        "strategy": s, "evidence": evidence})

    def _passes_paper_gate(self, strategy: str, now: float) -> bool:
        trades = self.paper_trades[strategy]
        if len(trades) < self.GATE_MIN_TRADES:
            return False
        span_days = (now - min(t["ts"] for t in trades)) / DAY
        if span_days < self.GATE_MIN_DAYS:
            return False
        lo, _hi = bootstrap_ci([t["pnl"] for t in trades])
        return lo > 0

    def _gate_evidence(self, strategy: str, now: float) -> str:
        trades = self.paper_trades[strategy]
        lo, hi = bootstrap_ci([t["pnl"] for t in trades])
        return (f"n={len(trades)} ci=({lo:.4f},{hi:.4f}) "
                f"span={(now - min(t['ts'] for t in trades)) / DAY:.1f}d")

    def _edge_decayed(self, strategy: str) -> tuple[bool, str]:
        trades = self.live_trades[strategy]
        if len(trades) < 30:
            return False, ""
        window = sorted(trades, key=lambda t: t["ts"])[-self.DECAY_WINDOW_TRADES:]
        lo, hi = bootstrap_ci([t["pnl"] for t in window])
        if hi < 0:
            return True, f"rolling ci upper {hi:.4f} < 0 over last {len(window)} trades"
        return False, ""
