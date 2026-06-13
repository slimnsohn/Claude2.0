"""Tests for analysis components."""

import pytest
from analysis.source_quirks import find_relevant_quirks, format_quirks_for_prompt
from analysis.prompts import (
    get_primary_prompt, get_rules_adjusted_prompt,
    get_cross_platform_prompt, PROMPT_VERSION,
)


class TestSourceQuirks:
    def test_finds_bls_cpi(self):
        rules = "Resolves based on Bureau of Labor Statistics CPI-U report."
        quirks = find_relevant_quirks(rules)
        assert len(quirks) >= 1
        sources = [q["source"] for q in quirks]
        assert "BLS CPI" in sources

    def test_finds_wikipedia(self):
        rules = "Resolves based on the Wikipedia article for this topic."
        quirks = find_relevant_quirks(rules)
        sources = [q["source"] for q in quirks]
        assert "Wikipedia" in sources

    def test_no_match_for_unrelated(self):
        rules = "Resolves YES if the stock price exceeds $100."
        quirks = find_relevant_quirks(rules)
        assert len(quirks) == 0

    def test_format_empty_quirks(self):
        assert format_quirks_for_prompt([]) == ""

    def test_format_quirks_contains_gotcha(self):
        quirks = find_relevant_quirks("Based on Bureau of Labor Statistics CPI data")
        text = format_quirks_for_prompt(quirks)
        assert "Gotcha" in text


class TestPromptTemplates:
    def test_primary_prompt_has_all_fields(self):
        prompt = get_primary_prompt(
            platform="polymarket",
            title="Test Market",
            rules="Test rules",
            yes_price=0.65,
            end_date="2026-12-31",
        )
        assert "PLATFORM: polymarket" in prompt
        assert "TITLE: Test Market" in prompt
        assert "Test rules" in prompt
        assert "0.65" in prompt
        assert "DATE_BOUNDARY" in prompt
        assert "HIDDEN_TECHNICALITY" in prompt

    def test_rules_adjusted_prompt(self):
        prompt = get_rules_adjusted_prompt(
            title="Test",
            rules="Some rules",
            key_discrepancy="Date mismatch",
            yes_price=0.70,
        )
        assert "Date mismatch" in prompt
        assert "0.70" in prompt

    def test_cross_platform_prompt(self):
        prompt = get_cross_platform_prompt(
            poly_title="Poly title",
            poly_rules="Poly rules",
            poly_end_date="2026-12-31",
            kalshi_title="Kalshi title",
            kalshi_rules="Kalshi rules",
            kalshi_end_date="2026-12-31",
        )
        assert "POLYMARKET" in prompt
        assert "KALSHI" in prompt
        assert "Poly title" in prompt
        assert "Kalshi title" in prompt

    def test_prompt_version_is_set(self):
        assert PROMPT_VERSION == "v1"
