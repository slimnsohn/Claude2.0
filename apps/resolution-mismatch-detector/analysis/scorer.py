"""Priority scoring and pre-scan queue logic."""

import math
import logging

from config import (
    SEVERITY_WEIGHTS, LIQUIDITY_LOG_CAP, POSITION_MULTIPLIER,
    MIN_VOLUME_THRESHOLD,
)

logger = logging.getLogger(__name__)


def calculate_priority(analysis: dict, market: dict, has_position: bool = False) -> float:
    """
    Priority = severity_weight x liquidity_score x price_extremity x position_multiplier

    Changed from pure multiplication to additive-weighted so no single null
    factor zeroes out the whole score. Severity is the dominant signal.

    Score range: 0.0 to ~2.0 (higher = more actionable)
    """
    severity_w = SEVERITY_WEIGHTS.get(analysis.get("severity", "none"), 0.0)
    if severity_w == 0:
        return 0.0

    # Liquidity: 0.1 floor so unknown-volume markets still get some score
    volume = 0
    try:
        volume = float(market.get("volume") or 0)
    except (ValueError, TypeError):
        pass
    liquidity_score = min(1.0, math.log10(max(volume, 1)) / LIQUIDITY_LOG_CAP) if volume > 0 else 0.1

    # Price extremity: 0.3 floor for null/unknown prices
    # (missing price means we can't confirm it's priced correctly — worth flagging)
    price = None
    try:
        price = float(market.get("current_yes_price")) if market.get("current_yes_price") is not None else None
    except (ValueError, TypeError):
        pass

    if price is not None:
        price_extremity = max(0.1, abs(price - 0.5) * 2)
    else:
        price_extremity = 0.3  # unknown price — moderate default

    position_mult = POSITION_MULTIPLIER if has_position else 1.0

    # Weighted: severity is 60% of score, liquidity 20%, price 20%
    score = (severity_w * 0.6 + liquidity_score * 0.2 + price_extremity * 0.2) * position_mult
    return round(score, 4)


def build_scan_queue(markets: list[dict], position_checker=None) -> list[dict]:
    """
    Score markets BEFORE analysis to prioritize Claude CLI spend.
    Returns markets sorted by pre_score descending.
    No min_volume filter here — let the caller decide.
    """
    scored = []
    for m in markets:
        volume = 0
        try:
            volume = float(m.get("volume") or 0)
        except (ValueError, TypeError):
            pass

        book_depth = m.get("book_depth_5pct")
        depth_factor = 1.0 if book_depth and book_depth > 1000 else 0.5

        has_pos = False
        if position_checker:
            has_pos = position_checker(m.get("id", ""))
        pos_factor = POSITION_MULTIPLIER if has_pos else 1.0

        # Floor at 1.0 so zero-volume markets still get queued (just low priority)
        pre_score = math.log10(max(volume, 10)) * depth_factor * pos_factor

        m["pre_score"] = round(pre_score, 4)
        scored.append(m)

    scored.sort(key=lambda x: x["pre_score"], reverse=True)
    logger.info(f"Scan queue: {len(scored)} markets")
    return scored


def calculate_price_divergence(rules_adjusted_prob: float, market_price: float) -> float:
    """Calculate divergence between rules-adjusted probability and market price."""
    return round(rules_adjusted_prob - market_price, 4)
