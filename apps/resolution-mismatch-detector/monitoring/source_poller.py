"""Resolution source monitors — detect when external sources update."""

import hashlib
import json
import logging

import requests

from analysis.source_quirks import SOURCE_QUIRKS

logger = logging.getLogger(__name__)


def poll_source(source_name: str, db) -> list[dict]:
    """
    Check if a resolution source has updated.
    Compare content hash to detect changes.
    When changed, cross-reference linked markets.

    Returns list of flagged markets if source updated, empty list otherwise.
    """
    source_config = SOURCE_QUIRKS.get(source_name, {})
    url = source_config.get("url")
    if not url:
        logger.debug(f"No URL for source {source_name}, skipping")
        return []

    try:
        resp = requests.get(url, timeout=30, headers={
            "User-Agent": "ResolutionMismatchDetector/1.0"
        })
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning(f"Failed to poll {source_name}: {e}")
        # Source unreachable — flag linked markets
        stored = db.get_source_monitor(source_name)
        if stored:
            linked_ids = json.loads(stored.get("linked_market_ids") or "[]")
            return [{
                "market_id": mid,
                "source": source_name,
                "event": "SOURCE_UNREACHABLE",
                "urgency": "medium",
            } for mid in linked_ids]
        return []

    content_hash = hashlib.sha256(resp.text.encode()).hexdigest()
    stored = db.get_source_monitor(source_name)

    if stored and stored["content_hash"] != content_hash:
        logger.info(f"Source {source_name} content changed!")
        linked_ids = json.loads(stored.get("linked_market_ids") or "[]")

        flagged = []
        for market_id in linked_ids:
            analysis = db.get_latest_analysis(market_id)
            flagged.append({
                "market_id": market_id,
                "source": source_name,
                "event": "SOURCE_UPDATED",
                "mismatch_found": bool(analysis and analysis["mismatch_found"]),
                "urgency": "IMMEDIATE" if (analysis and analysis["mismatch_found"]) else "medium",
            })

        db.update_source_monitor(source_name, content_hash)
        return flagged

    # No change — just update last_checked timestamp
    db.upsert_source_monitor(source_name, content_hash=content_hash)
    return []


def poll_all_sources(db) -> list[dict]:
    """Poll all known resolution sources. Returns combined list of flagged markets."""
    all_flagged = []
    for source_name in SOURCE_QUIRKS:
        flagged = poll_source(source_name, db)
        all_flagged.extend(flagged)
    return all_flagged
