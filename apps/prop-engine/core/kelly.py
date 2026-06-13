"""Fractional Kelly stake sizing."""
from __future__ import annotations


def _american_to_decimal(american: int) -> float:
    if american >= 100:
        return 1.0 + american / 100.0
    return 1.0 + 100.0 / abs(american)


def fractional_kelly_stake(
    posterior_prob: float,
    american_odds: int,
    bankroll: float,
    kelly_fraction: float,
    max_stake_pct: float,
    min_bet: float,
) -> float:
    """Return recommended stake in dollars. Returns 0 if no edge or below min."""
    if bankroll <= 0:
        raise ValueError("bankroll must be positive")
    if not (0 < posterior_prob < 1):
        return 0.0

    decimal = _american_to_decimal(american_odds)
    b = decimal - 1.0
    if b <= 0:
        return 0.0

    edge = decimal * posterior_prob - 1.0
    if edge <= 0:
        return 0.0

    f_full = edge / b
    raw = bankroll * f_full * kelly_fraction
    cap = bankroll * max_stake_pct
    stake = min(raw, cap)
    if stake < min_bet:
        return 0.0
    return round(stake, 2)
