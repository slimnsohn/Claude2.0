"""De-vigging — convert vigged American odds to fair (no-vig) probabilities.

Implements both the simple "power" / multiplicative method and Shin's (1993)
method which models the proportion of informed/insider money and gives better
fair probabilities for markets with favorite-longshot bias (player props).
"""
from __future__ import annotations
import math
from typing import Sequence
from scipy.optimize import brentq


def american_to_implied(american: int) -> float:
    if american == 0 or -100 < american < 100:
        raise ValueError(f"Invalid American odds: {american}")
    if american >= 100:
        return 100.0 / (american + 100.0)
    return abs(american) / (abs(american) + 100.0)


def devig_two_way_power(odds_a: int, odds_b: int) -> tuple[float, float]:
    ia = american_to_implied(odds_a)
    ib = american_to_implied(odds_b)
    overround = ia + ib
    return ia / overround, ib / overround


def _shin_fair_from_implied(p_imp: float, overround: float, z: float) -> float:
    inside = z * z + 4.0 * (1.0 - z) * (p_imp * p_imp) / overround
    if inside < 0:
        return p_imp / overround
    return (math.sqrt(inside) - z) / (2.0 * (1.0 - z))


def devig_two_way_shin(odds_a: int, odds_b: int) -> tuple[float, float]:
    """Shin's method. Solves for z (insider proportion) such that the two
    fair probabilities sum to 1.0, then returns them. Falls back to power
    method on solver failure."""
    ia = american_to_implied(odds_a)
    ib = american_to_implied(odds_b)
    overround = ia + ib

    if abs(overround - 1.0) < 1e-9:
        return ia, ib

    def objective(z: float) -> float:
        fa = _shin_fair_from_implied(ia, overround, z)
        fb = _shin_fair_from_implied(ib, overround, z)
        return fa + fb - 1.0

    try:
        z_solved = brentq(objective, 1e-6, 0.30, xtol=1e-8, maxiter=200)
    except (ValueError, RuntimeError):
        return devig_two_way_power(odds_a, odds_b)

    fa = _shin_fair_from_implied(ia, overround, z_solved)
    fb = _shin_fair_from_implied(ib, overround, z_solved)
    total = fa + fb
    return fa / total, fb / total


def enforce_monotonic_ladder(probs: Sequence[float]) -> list[float]:
    """Pool-Adjacent-Violators to enforce a non-increasing sequence.

    Result has the same length as input; positions in the same pooled
    block share the pooled (weighted) mean.
    """
    n = len(probs)
    if n <= 1:
        return [float(x) for x in probs]

    # Each block is a list of original indices
    blocks: list[list[int]] = [[i] for i in range(n)]
    values: list[float] = [float(x) for x in probs]
    weights: list[float] = [1.0] * n

    i = 0
    while i < len(values) - 1:
        if values[i] >= values[i + 1]:
            i += 1
            continue
        # Violation: pool block i and block i+1
        new_w = weights[i] + weights[i + 1]
        new_v = (values[i] * weights[i] + values[i + 1] * weights[i + 1]) / new_w
        blocks[i] = blocks[i] + blocks[i + 1]
        values[i] = new_v
        weights[i] = new_w
        del blocks[i + 1]
        del values[i + 1]
        del weights[i + 1]
        if i > 0:
            i -= 1

    out = [0.0] * n
    for block_value, idxs in zip(values, blocks):
        for j in idxs:
            out[j] = block_value
    return out
