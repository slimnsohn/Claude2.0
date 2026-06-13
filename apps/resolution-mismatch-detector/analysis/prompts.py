"""Versioned prompt templates for Claude analysis."""

PROMPT_VERSION = "v1"

SYSTEM_PROMPT = """You are a prediction market resolution rules analyst. Your job is to identify \
mismatches between what a market's title implies and what its resolution rules \
actually specify.

You think like a lawyer reading a contract, not a casual bettor reading a headline.

Respond ONLY with valid JSON. No markdown, no preamble, no explanation outside the JSON."""

PRIMARY_ANALYSIS_TEMPLATE = """Analyze this prediction market for resolution rule mismatches.

PLATFORM: {platform}
TITLE: {title}
RESOLUTION RULES:
{rules}

CURRENT YES PRICE: {yes_price}
END DATE: {end_date}

Check for these 6 mismatch categories:

1. DATE_BOUNDARY: Title implies a timeframe but rules specify a different cutoff
   (e.g., title says "in 2026" but rules say "by March 31, 2026 11:59 PM ET")

2. SOURCE_SPECIFIC: Resolution depends on one specific source, not general consensus
   (e.g., "Will X happen?" resolves based solely on one agency's report)

3. CONDITIONAL_LOGIC: Rules contain conditions that contradict the obvious reading
   (e.g., "Will X reach $100?" but rules say "based on closing price" not intraday)

4. AMBIGUOUS_LANGUAGE: Rules use terms that could be interpreted multiple ways
   (e.g., "significant increase" without defining threshold)

5. INCOMPLETE_COVERAGE: YES + NO don't cover all possible outcomes, or edge cases
   would cause unexpected resolution (e.g., market voids if event postponed)

6. HIDDEN_TECHNICALITY: Rules contain a technical detail that meaningfully changes
   the market's expected resolution vs naive reading (e.g., "seasonally adjusted"
   vs "non-adjusted" figures)

If no mismatch exists, say NONE.

{source_quirks_context}

Respond with this exact JSON structure:
{{
  "mismatch_found": true/false,
  "severity": "high" | "medium" | "low" | "none",
  "categories": ["DATE_BOUNDARY", ...],
  "retail_assumption": "What a casual trader would assume from the title",
  "actual_resolution": "What the rules actually specify",
  "key_discrepancy": "One-sentence summary of the gap",
  "confidence": 0.0-1.0,
  "edge_direction": "YES" | "NO" | "UNCLEAR",
  "reasoning": "Brief explanation of the mismatch"
}}"""

RULES_ADJUSTED_PROBABILITY_TEMPLATE = """Given this mismatch analysis, estimate the rules-adjusted probability.

TITLE: {title}
RESOLUTION RULES: {rules}
MISMATCH SUMMARY: {key_discrepancy}
CURRENT MARKET PRICE (implied probability): {yes_price}

Consider the specific resolution criteria, not the casual interpretation.
Factor in any known source quirks: {source_quirks}

Respond with JSON only:
{{
  "rules_adjusted_probability": 0.0-1.0,
  "market_price": {yes_price},
  "divergence": <rules_adjusted - market_price>,
  "confidence_in_estimate": 0.0-1.0,
  "reasoning": "Brief explanation"
}}"""

CROSS_PLATFORM_DIFF_TEMPLATE = """Compare the resolution rules for what appears to be the same event on two platforms.

POLYMARKET:
  Title: {poly_title}
  Rules: {poly_rules}
  End Date: {poly_end_date}

KALSHI:
  Title: {kalshi_title}
  Rules: {kalshi_rules}
  End Date: {kalshi_end_date}

Identify:
1. Do these markets resolve on the same event?
2. Are the resolution criteria materially different?
3. Could one resolve YES while the other resolves NO for the same real-world outcome?
4. What specific rule differences create divergence risk?

Respond with JSON only:
{{
  "same_event": true/false,
  "same_event_confidence": 0.0-1.0,
  "rules_materially_different": true/false,
  "divergent_resolution_possible": true/false,
  "key_differences": ["difference 1", "difference 2", ...],
  "arb_opportunity": true/false,
  "arb_direction": "Description of which side on which platform",
  "reasoning": "Brief explanation"
}}"""


def get_primary_prompt(platform: str, title: str, rules: str,
                       yes_price: float, end_date: str,
                       source_quirks_context: str = "") -> str:
    """Build the primary analysis prompt."""
    return PRIMARY_ANALYSIS_TEMPLATE.format(
        platform=platform,
        title=title,
        rules=rules,
        yes_price=f"{yes_price:.2f}" if yes_price else "N/A",
        end_date=end_date or "N/A",
        source_quirks_context=source_quirks_context,
    )


def get_rules_adjusted_prompt(title: str, rules: str, key_discrepancy: str,
                              yes_price: float, source_quirks: str = "") -> str:
    """Build the rules-adjusted probability follow-up prompt."""
    return RULES_ADJUSTED_PROBABILITY_TEMPLATE.format(
        title=title,
        rules=rules,
        key_discrepancy=key_discrepancy,
        yes_price=f"{yes_price:.2f}" if yes_price else "N/A",
        source_quirks=source_quirks or "None known",
    )


def get_cross_platform_prompt(poly_title: str, poly_rules: str, poly_end_date: str,
                              kalshi_title: str, kalshi_rules: str,
                              kalshi_end_date: str) -> str:
    """Build the cross-platform rule diff prompt."""
    return CROSS_PLATFORM_DIFF_TEMPLATE.format(
        poly_title=poly_title,
        poly_rules=poly_rules,
        poly_end_date=poly_end_date or "N/A",
        kalshi_title=kalshi_title,
        kalshi_rules=kalshi_rules,
        kalshi_end_date=kalshi_end_date or "N/A",
    )
