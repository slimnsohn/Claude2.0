"""Hash-based rule change detection across market snapshots."""

import logging
from datetime import datetime

from ingestion.normalizer import compute_rules_hash

logger = logging.getLogger(__name__)


def check_for_rule_changes(markets: list[dict], db) -> list[dict]:
    """
    Compare current market rules against stored snapshots.
    Returns list of markets where rules have changed.
    """
    changes = []

    for market in markets:
        market_id = market["id"]
        current_rules = market.get("resolution_rules", "")
        current_hash = compute_rules_hash(current_rules)

        latest_snapshot = db.get_latest_snapshot(market_id)

        if latest_snapshot is None:
            # First time seeing this market — store initial snapshot
            db.insert_rule_snapshot(market_id, current_rules, current_hash)
            continue

        if latest_snapshot["rules_hash"] != current_hash:
            logger.warning(f"Rule change detected for {market_id}")

            # Store new snapshot
            db.insert_rule_snapshot(market_id, current_rules, current_hash)

            changes.append({
                "market_id": market_id,
                "old_rules": latest_snapshot["resolution_rules"],
                "new_rules": current_rules,
                "old_hash": latest_snapshot["rules_hash"],
                "new_hash": current_hash,
                "detected_at": datetime.utcnow().isoformat(),
            })

    logger.info(f"Rule change check: {len(changes)} changes in {len(markets)} markets")
    return changes
