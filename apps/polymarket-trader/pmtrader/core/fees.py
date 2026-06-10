"""Fee model.

Recon (2026-06-09) confirmed Gamma publishes a per-market feeSchedule
{exponent, rate, takerOnly, rebateRate} plus a feesEnabled flag:
    taker_fee_per_share = rate * (p * (1 - p)) ** exponent
Cross-checked against the published schedule (general 0.05 -> $1.25/100 at
p=0.5; sports 0.03 -> $0.75/100). The API schedule always wins; the category
table below is a fallback for markets where Gamma omits it, derived from the
published per-100-share peaks (rate = 4 * peak_per_share).
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class FeeSchedule(BaseModel):
    exponent: float = 1.0
    rate: float
    taker_only: bool = True
    rebate_rate: float = 0.0


CATEGORY_RATE = {  # fallback rates; API feeSchedule overrides
    "crypto": 0.072,        # $1.80/100 peak
    "economics": 0.05,      # $1.25/100
    "culture": 0.05,
    "weather": 0.05,
    "politics": 0.04,       # $1.00/100
    "finance": 0.04,
    "tech": 0.04,
    "mentions": 0.04,
    "sports": 0.03,         # $0.75/100
    "geopolitics": 0.0,     # fee-free
    "world": 0.0,
}
DEFAULT_RATE = 0.05  # unknown category -> assume mid-tier; conservative for EV


def _rate_and_exponent(schedule: Optional[FeeSchedule], category: Optional[str]) -> tuple[float, float]:
    if schedule is not None:
        return schedule.rate, schedule.exponent
    if category is not None:
        return CATEGORY_RATE.get(category.lower(), DEFAULT_RATE), 1.0
    return DEFAULT_RATE, 1.0


def taker_fee_per_share(
    price: float,
    schedule: Optional[FeeSchedule] = None,
    category: Optional[str] = None,
    fees_enabled: bool = True,
) -> float:
    if not fees_enabled:
        return 0.0
    rate, exponent = _rate_and_exponent(schedule, category)
    return rate * (price * (1.0 - price)) ** exponent


def maker_fee_per_share(
    price: float,
    schedule: Optional[FeeSchedule] = None,
    category: Optional[str] = None,
    fees_enabled: bool = True,
) -> float:
    if schedule is not None and not schedule.taker_only:
        return taker_fee_per_share(price, schedule, category, fees_enabled)
    return 0.0


def maker_rebate_rate(schedule: Optional[FeeSchedule]) -> float:
    """Fraction of collected taker fees redistributed to makers (daily)."""
    return schedule.rebate_rate if schedule is not None else 0.0


def order_taker_fee(
    price: float,
    size: float,
    schedule: Optional[FeeSchedule] = None,
    category: Optional[str] = None,
    fees_enabled: bool = True,
) -> float:
    return size * taker_fee_per_share(price, schedule, category, fees_enabled)
