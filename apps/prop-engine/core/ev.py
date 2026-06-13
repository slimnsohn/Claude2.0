"""EV calculation and Normal-distribution μ inversion for market-anchored model."""
from __future__ import annotations
from scipy.stats import norm


def _american_to_decimal(american: int) -> float:
    if american >= 100:
        return 1.0 + american / 100.0
    return 1.0 + 100.0 / abs(american)


def edge_pct(posterior_prob: float, american_odds: int) -> float:
    """edge = decimal_odds * p - 1.  Positive = +EV."""
    return _american_to_decimal(american_odds) * posterior_prob - 1.0


def ev_dollars(edge_pct_val: float, stake: float) -> float:
    return edge_pct_val * stake


def extract_implied_mu(consensus_prob: float, line: float, sigma: float) -> float:
    """Given a consensus P(stat > line) and σ, return the implied mean μ
    under a Normal(μ, σ) model."""
    if sigma <= 0:
        raise ValueError("sigma must be positive")
    if not (0 < consensus_prob < 1):
        return line
    z = norm.ppf(1.0 - consensus_prob)
    return line - sigma * z


def posterior_prob_from_mu(mu: float, line: float, sigma: float) -> float:
    """P(X > line) where X ~ Normal(mu, sigma)."""
    if sigma <= 0:
        raise ValueError("sigma must be positive")
    return float(1.0 - norm.cdf((line - mu) / sigma))
