"""Follow-up analysis: rules-adjusted probability estimation."""

import logging

from analysis.claude_client import ClaudeClient
from analysis.prompts import get_rules_adjusted_prompt
from analysis.source_quirks import find_relevant_quirks, format_quirks_for_prompt

logger = logging.getLogger(__name__)


def estimate_rules_adjusted_probability(
    client: ClaudeClient,
    market: dict,
    analysis: dict,
) -> dict:
    """
    Given a mismatch analysis, ask Claude to estimate the rules-adjusted probability.
    Returns parsed response with rules_adjusted_probability, divergence, etc.
    """
    quirks = find_relevant_quirks(market.get("resolution_rules", ""))
    quirks_text = format_quirks_for_prompt(quirks) if quirks else ""

    prompt = get_rules_adjusted_prompt(
        title=market["title"],
        rules=market["resolution_rules"],
        key_discrepancy=analysis.get("key_discrepancy", ""),
        yes_price=market.get("current_yes_price", 0.5),
        source_quirks=quirks_text,
    )

    result = client.analyze(prompt)

    # Remove meta for clean return, but keep for logging
    meta = result.pop("_meta", {})
    logger.info(
        f"Rules-adjusted prob for {market['id']}: "
        f"{result.get('rules_adjusted_probability', 'N/A')} "
        f"(divergence: {result.get('divergence', 'N/A')})"
    )

    result["_meta"] = meta
    return result
