"""Normalize platform-specific market data into common schema."""

import hashlib
import json
from datetime import datetime


def normalize_market(raw: dict, platform: str) -> dict:
    """
    Convert a dict from PolymarketClient or KalshiClient into the markets table schema.

    Expected input keys: platform_id, title, resolution_rules, end_date,
    volume, liquidity, current_yes_price, raw_json.

    Returns a dict ready for db.upsert_market().
    """
    now = datetime.utcnow().isoformat()
    raw_json = raw.get("raw_json")
    if raw_json and not isinstance(raw_json, str):
        raw_json = json.dumps(raw_json)

    return {
        "id": f"{platform}:{raw['platform_id']}",
        "platform": platform,
        "title": raw["title"],
        "resolution_rules": raw["resolution_rules"],
        "end_date": raw.get("end_date"),
        "volume": raw.get("volume"),
        "liquidity": raw.get("liquidity"),
        "current_yes_price": raw.get("current_yes_price"),
        "raw_json": raw_json,
        "first_seen_at": now,
        "last_updated_at": now,
    }


def compute_rules_hash(rules: str) -> str:
    """SHA256 hash of resolution rules text for change detection."""
    return hashlib.sha256(rules.strip().encode()).hexdigest()


def detect_rule_change(current_rules: str, stored_hash: str | None) -> bool:
    """Return True if rules have changed (hash mismatch or no prior hash)."""
    if stored_hash is None:
        return True
    return compute_rules_hash(current_rules) != stored_hash
