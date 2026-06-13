"""Historical resolution backfill pipeline."""

import logging
from datetime import datetime

from analysis.claude_client import ClaudeClient
from db.database import Database
from ingestion.polymarket import PolymarketClient
from ingestion.kalshi import KalshiClient

logger = logging.getLogger(__name__)


def fetch_resolved_markets(platform: str, limit: int = 500) -> list[dict]:
    """Fetch resolved/closed markets from a platform."""
    if platform == "polymarket":
        client = PolymarketClient()
        return client.fetch_resolved_markets(limit=limit)
    elif platform == "kalshi":
        client = KalshiClient()
        return client.fetch_resolved_markets(limit=limit)
    return []


def analyze_resolution_accuracy(client: ClaudeClient, market: dict) -> dict:
    """Ask Claude: did this market resolve per rules or per title implication?"""
    prompt = f"""This prediction market has resolved. Analyze whether it resolved according to
its resolution rules or according to what the title implied.

PLATFORM: {market.get('platform', 'unknown')}
TITLE: {market.get('title', 'N/A')}
RESOLUTION RULES: {market.get('resolution_rules', 'N/A')}
RESOLUTION OUTCOME: {market.get('outcome', 'N/A')}

Respond with JSON only:
{{
  "resolved_per_rules": true/false,
  "explanation": "Brief explanation of how it resolved and whether title-readers would have been surprised",
  "surprise_factor": "high" | "medium" | "low" | "none"
}}"""

    return client.analyze(prompt)


def backfill_resolved_markets(db: Database = None, client: ClaudeClient = None):
    """
    Pull resolved markets from both platforms.
    For each, determine: did it resolve per rules or per title implication?
    Build calibration dataset for severity scorer.
    """
    db = db or Database()
    client = client or ClaudeClient()

    for platform in ["polymarket", "kalshi"]:
        logger.info(f"Fetching resolved markets from {platform}...")
        try:
            resolved = fetch_resolved_markets(platform, limit=500)
        except Exception as e:
            logger.error(f"Failed to fetch resolved markets from {platform}: {e}")
            continue

        for market in resolved:
            market_id = f"{platform}:{market.get('platform_id', market.get('id', ''))}"

            # Check if we flagged this pre-resolution
            prior_analysis = db.get_latest_analysis(market_id)

            audit_entry = {
                "market_id": market_id,
                "resolved_at": market.get("resolved_at", datetime.utcnow().isoformat()),
                "resolution_outcome": market.get("outcome", "UNKNOWN"),
                "mismatch_was_flagged": 1 if prior_analysis and prior_analysis["mismatch_found"] else 0,
                "mismatch_severity_at_flag": prior_analysis["severity"] if prior_analysis else None,
                "price_at_flag": prior_analysis["market_price_at_analysis"] if prior_analysis else None,
                "price_at_resolution": market.get("final_price"),
            }

            try:
                audit_analysis = analyze_resolution_accuracy(client, market)
                audit_entry["resolved_per_rules"] = 1 if audit_analysis.get("resolved_per_rules") else 0
                audit_entry["notes"] = audit_analysis.get("explanation", "")
            except Exception as e:
                logger.warning(f"Failed to analyze resolution for {market_id}: {e}")
                audit_entry["resolved_per_rules"] = None
                audit_entry["notes"] = f"Analysis failed: {e}"

            db.insert_resolution_audit(audit_entry)

    logger.info("Backfill complete")
