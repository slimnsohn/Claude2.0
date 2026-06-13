"""Cross-platform market matching using fuzzy title + date proximity."""

import logging
from datetime import datetime, timedelta

from rapidfuzz import fuzz, process

logger = logging.getLogger(__name__)


def dates_within_days(date1: str | None, date2: str | None, days: int = 7) -> bool:
    """Check if two ISO date strings are within N days of each other."""
    if not date1 or not date2:
        return False
    try:
        d1 = datetime.fromisoformat(date1.replace("Z", "+00:00"))
        d2 = datetime.fromisoformat(date2.replace("Z", "+00:00"))
        return abs((d1 - d2).days) <= days
    except (ValueError, TypeError):
        return False


def find_cross_platform_matches(
    poly_markets: list[dict],
    kalshi_markets: list[dict],
    threshold: float = 0.65,
) -> list[dict]:
    """
    Match markets across platforms by:
    1. Fuzzy title similarity (rapidfuzz token_sort_ratio)
    2. Date proximity (end dates within 7 days)
    3. Combined confidence score

    Returns candidate pairs above threshold for Claude verification.
    """
    if not poly_markets or not kalshi_markets:
        return []

    # Build lookup dict for kalshi
    kalshi_titles = {km["id"]: km["title"] for km in kalshi_markets}
    kalshi_by_id = {km["id"]: km for km in kalshi_markets}

    matches = []
    for pm in poly_markets:
        candidates = process.extract(
            pm["title"],
            kalshi_titles,
            scorer=fuzz.token_sort_ratio,
            limit=5,
        )

        for _title, score, kalshi_id in candidates:
            if score < threshold * 100:
                continue

            km = kalshi_by_id[kalshi_id]
            date_match = dates_within_days(pm.get("end_date"), km.get("end_date"), 7)
            title_sim = score / 100.0
            match_confidence = title_sim * (1.0 if date_match else 0.7)

            if match_confidence >= threshold:
                matches.append({
                    "polymarket_id": pm["id"],
                    "kalshi_id": km["id"],
                    "poly_title": pm["title"],
                    "kalshi_title": km["title"],
                    "title_similarity": round(title_sim, 3),
                    "date_match": 1 if date_match else 0,
                    "match_confidence": round(match_confidence, 3),
                })

    # Deduplicate: keep highest confidence per pair
    seen = set()
    deduped = []
    for m in sorted(matches, key=lambda x: x["match_confidence"], reverse=True):
        key = (m["polymarket_id"], m["kalshi_id"])
        if key not in seen:
            seen.add(key)
            deduped.append(m)

    logger.info(f"Found {len(deduped)} cross-platform match candidates")
    return deduped
