"""Statistical machinery: bootstrap CIs, walk-forward splits, risk metrics.

These functions decide whether an edge is real. They must be deterministic
(seeded) and conservative. Used by the backtester, the paper gate, and the
allocator's edge-decay detection.
"""
from __future__ import annotations

import numpy as np

SHARPE_CAP = 100.0  # zero-volatility guard


def bootstrap_ci(samples: list[float], n_boot: int = 2000, alpha: float = 0.05,
                 seed: int = 0) -> tuple[float, float]:
    """Percentile bootstrap CI of the mean. Empty -> (0, 0)."""
    if not samples:
        return (0.0, 0.0)
    xs = np.asarray(samples, dtype=float)
    if len(xs) == 1:
        return (float(xs[0]), float(xs[0]))
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(xs), size=(n_boot, len(xs)))
    means = xs[idx].mean(axis=1)
    lo, hi = np.quantile(means, [alpha / 2, 1 - alpha / 2])
    return (float(lo), float(hi))


def walk_forward(n: int, train: int, test: int) -> list[tuple[range, range]]:
    """Rolling out-of-sample folds: fit on train window, evaluate on the next
    test window, step forward by test. Evaluation indices never overlap any
    training index of their own fold."""
    folds = []
    start = 0
    while start + train + test <= n:
        folds.append((range(start, start + train),
                      range(start + train, start + train + test)))
        start += test
    return folds


def max_drawdown(equity: list[float]) -> float:
    """Largest peak-to-trough fractional decline."""
    if not equity:
        return 0.0
    peak = equity[0]
    worst = 0.0
    for v in equity:
        peak = max(peak, v)
        if peak > 0:
            worst = max(worst, (peak - v) / peak)
    return worst


def sharpe(returns: list[float]) -> float:
    """Mean/std of per-period returns (not annualized — comparative use only)."""
    if not returns:
        return 0.0
    xs = np.asarray(returns, dtype=float)
    mu = xs.mean()
    sd = xs.std(ddof=1) if len(xs) > 1 else 0.0
    if sd == 0.0:
        return 0.0 if mu == 0.0 else (SHARPE_CAP if mu > 0 else -SHARPE_CAP)
    return float(mu / sd)
