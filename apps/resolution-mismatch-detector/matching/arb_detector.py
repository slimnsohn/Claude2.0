"""Structural arbitrage detection from cross-platform rule differences."""

import logging

logger = logging.getLogger(__name__)


def detect_structural_arb(
    match: dict,
    poly_price: float,
    kalshi_price: float,
    rule_diff: dict,
) -> dict | None:
    """
    If rules differ such that one could resolve YES while other resolves NO,
    AND prices don't reflect this, that's a structural arb.

    Args:
        match: Cross-platform match dict with poly/kalshi IDs
        poly_price: Current Polymarket YES price
        kalshi_price: Current Kalshi YES price
        rule_diff: Claude's cross-platform diff analysis result

    Returns:
        Arb signal dict or None if no arb detected.
    """
    if not rule_diff.get("divergent_resolution_possible"):
        return None

    price_gap = abs(poly_price - kalshi_price)

    # Both priced similarly but could resolve differently — market hasn't noticed
    if price_gap < 0.15:
        arb = {
            "type": "structural_arb",
            "polymarket_id": match["polymarket_id"],
            "kalshi_id": match["kalshi_id"],
            "poly_price": poly_price,
            "kalshi_price": kalshi_price,
            "price_gap": round(price_gap, 4),
            "rule_divergence": rule_diff.get("key_differences", []),
            "suggested_action": rule_diff.get("arb_direction", "Review manually"),
            "urgency": "high",
        }
        logger.warning(
            f"Structural arb detected: {match['polymarket_id']} vs {match['kalshi_id']} "
            f"(gap={price_gap:.2%})"
        )
        return arb

    return None
