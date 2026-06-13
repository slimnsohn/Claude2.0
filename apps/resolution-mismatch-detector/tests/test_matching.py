"""Tests for cross-platform matching and arb detection."""

import pytest
from matching.cross_platform import find_cross_platform_matches, dates_within_days
from matching.arb_detector import detect_structural_arb


class TestDatesWithinDays:
    def test_same_date(self):
        assert dates_within_days("2026-06-01", "2026-06-01") is True

    def test_within_range(self):
        assert dates_within_days("2026-06-01", "2026-06-05", days=7) is True

    def test_outside_range(self):
        assert dates_within_days("2026-06-01", "2026-06-20", days=7) is False

    def test_none_input(self):
        assert dates_within_days(None, "2026-06-01") is False
        assert dates_within_days("2026-06-01", None) is False


class TestCrossPlatformMatching:
    def test_identical_titles_match(self):
        poly = [{"id": "poly:1", "title": "Will Bitcoin reach 100k?", "end_date": "2026-12-31"}]
        kalshi = [{"id": "kalshi:1", "title": "Will Bitcoin reach 100k?", "end_date": "2026-12-31"}]
        matches = find_cross_platform_matches(poly, kalshi, threshold=0.6)
        assert len(matches) == 1
        assert matches[0]["match_confidence"] >= 0.9

    def test_no_match_different_topics(self):
        poly = [{"id": "poly:1", "title": "Will Bitcoin reach 100k?", "end_date": "2026-12-31"}]
        kalshi = [{"id": "kalshi:1", "title": "Will it rain tomorrow in Paris?", "end_date": "2026-01-01"}]
        matches = find_cross_platform_matches(poly, kalshi, threshold=0.65)
        assert len(matches) == 0

    def test_empty_inputs(self):
        assert find_cross_platform_matches([], []) == []
        assert find_cross_platform_matches([{"id": "a", "title": "test"}], []) == []


class TestArbDetector:
    def test_detects_arb_when_divergent_and_similar_price(self):
        match = {"polymarket_id": "poly:1", "kalshi_id": "kalshi:1"}
        diff = {
            "divergent_resolution_possible": True,
            "key_differences": ["Different deadline"],
            "arb_direction": "Buy YES on Poly, NO on Kalshi",
        }
        result = detect_structural_arb(match, 0.60, 0.62, diff)
        assert result is not None
        assert result["type"] == "structural_arb"
        assert result["urgency"] == "high"

    def test_no_arb_when_not_divergent(self):
        match = {"polymarket_id": "poly:1", "kalshi_id": "kalshi:1"}
        diff = {"divergent_resolution_possible": False}
        result = detect_structural_arb(match, 0.60, 0.62, diff)
        assert result is None

    def test_no_arb_when_prices_already_diverged(self):
        match = {"polymarket_id": "poly:1", "kalshi_id": "kalshi:1"}
        diff = {
            "divergent_resolution_possible": True,
            "key_differences": ["Different source"],
            "arb_direction": "Buy YES on Poly",
        }
        # Prices already 20% apart — market has noticed
        result = detect_structural_arb(match, 0.40, 0.60, diff)
        assert result is None
