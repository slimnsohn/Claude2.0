"""Tests for priority scoring and scan queue logic."""

import pytest
from analysis.scorer import calculate_priority, build_scan_queue


class TestCalculatePriority:
    def test_high_severity_high_volume_extreme_price(self):
        analysis = {"severity": "high"}
        market = {"volume": 1_000_000, "current_yes_price": 0.95}
        score = calculate_priority(analysis, market)
        assert score > 0.5

    def test_none_severity_returns_zero(self):
        analysis = {"severity": "none"}
        market = {"volume": 1_000_000, "current_yes_price": 0.95}
        score = calculate_priority(analysis, market)
        assert score == 0.0

    def test_low_volume_reduces_score(self):
        analysis = {"severity": "high"}
        high_vol = {"volume": 1_000_000, "current_yes_price": 0.90}
        low_vol = {"volume": 100, "current_yes_price": 0.90}
        assert calculate_priority(analysis, high_vol) > calculate_priority(analysis, low_vol)

    def test_50_50_price_gives_zero_extremity(self):
        analysis = {"severity": "high"}
        market = {"volume": 1_000_000, "current_yes_price": 0.50}
        score = calculate_priority(analysis, market)
        assert score == 0.0

    def test_position_multiplier(self):
        analysis = {"severity": "medium"}
        market = {"volume": 500_000, "current_yes_price": 0.80}
        no_pos = calculate_priority(analysis, market, has_position=False)
        with_pos = calculate_priority(analysis, market, has_position=True)
        assert with_pos == pytest.approx(no_pos * 2.0, rel=1e-2)


class TestBuildScanQueue:
    def test_filters_low_volume(self):
        markets = [
            {"id": "a", "volume": 100_000, "book_depth_5pct": 5000},
            {"id": "b", "volume": 500, "book_depth_5pct": 100},
        ]
        queue = build_scan_queue(markets)
        assert len(queue) == 1
        assert queue[0]["id"] == "a"

    def test_sorted_by_pre_score_descending(self):
        markets = [
            {"id": "low", "volume": 20_000, "book_depth_5pct": 500},
            {"id": "high", "volume": 5_000_000, "book_depth_5pct": 10_000},
            {"id": "mid", "volume": 200_000, "book_depth_5pct": 2000},
        ]
        queue = build_scan_queue(markets)
        assert queue[0]["id"] == "high"
        assert queue[-1]["id"] == "low"

    def test_position_boosts_score(self):
        markets = [
            {"id": "a", "volume": 100_000, "book_depth_5pct": 5000},
            {"id": "b", "volume": 100_000, "book_depth_5pct": 5000},
        ]
        queue = build_scan_queue(markets, position_checker=lambda mid: mid == "b")
        assert queue[0]["id"] == "b"
