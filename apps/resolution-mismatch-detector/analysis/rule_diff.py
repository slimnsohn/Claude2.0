"""Cross-platform rule diff and rule change impact analysis."""

import logging

from analysis.claude_client import ClaudeClient
from analysis.prompts import get_cross_platform_prompt

logger = logging.getLogger(__name__)


def analyze_cross_platform_diff(
    client: ClaudeClient,
    poly_market: dict,
    kalshi_market: dict,
) -> dict:
    """
    Compare resolution rules across two platforms for the same event.
    Returns parsed response with same_event, key_differences, arb_opportunity, etc.
    """
    prompt = get_cross_platform_prompt(
        poly_title=poly_market["title"],
        poly_rules=poly_market["resolution_rules"],
        poly_end_date=poly_market.get("end_date", ""),
        kalshi_title=kalshi_market["title"],
        kalshi_rules=kalshi_market["resolution_rules"],
        kalshi_end_date=kalshi_market.get("end_date", ""),
    )

    result = client.analyze(prompt)
    meta = result.pop("_meta", {})

    logger.info(
        f"Cross-platform diff: same_event={result.get('same_event')}, "
        f"arb={result.get('arb_opportunity')}"
    )

    result["_meta"] = meta
    return result


def analyze_rule_change_impact(
    client: ClaudeClient,
    market: dict,
    old_rules: str,
    new_rules: str,
    position: dict | None = None,
) -> dict:
    """
    Analyze the impact of a rule change on a market.
    If user has a position, include position context for urgency.
    """
    position_context = ""
    if position:
        position_context = (
            f"\nYOUR POSITION: {position['side']} @ {position['avg_price']:.2f} "
            f"x {position['quantity']}"
        )

    prompt = f"""A prediction market's resolution rules have changed. Analyze the impact.

PLATFORM: {market['platform']}
TITLE: {market['title']}

OLD RULES:
{old_rules}

NEW RULES:
{new_rules}
{position_context}

Respond with JSON only:
{{
  "material_change": true/false,
  "summary": "One-sentence summary of what changed",
  "impact_on_resolution": "How this changes expected resolution",
  "position_impact": "How this affects the position (if any)",
  "suggested_action": "What to do about it",
  "urgency": "high" | "medium" | "low"
}}"""

    result = client.analyze(prompt)
    meta = result.pop("_meta", {})
    result["_meta"] = meta
    return result
