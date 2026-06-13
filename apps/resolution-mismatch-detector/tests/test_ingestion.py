"""Tests for ingestion normalizer and rule change detection."""

import pytest
from ingestion.normalizer import normalize_market, compute_rules_hash, detect_rule_change


class TestNormalizeMarket:
    def test_polymarket_normalization(self):
        raw = {
            "platform_id": "abc123",
            "title": "Test Market",
            "resolution_rules": "Some rules",
            "end_date": "2026-12-31",
            "volume": 50000,
            "liquidity": 10000,
            "current_yes_price": 0.65,
            "raw_json": '{"test": true}',
        }
        result = normalize_market(raw, "polymarket")
        assert result["id"] == "polymarket:abc123"
        assert result["platform"] == "polymarket"
        assert result["title"] == "Test Market"
        assert "first_seen_at" in result
        assert "last_updated_at" in result

    def test_kalshi_normalization(self):
        raw = {
            "platform_id": "xyz789",
            "title": "Kalshi Market",
            "resolution_rules": "Rules here",
            "end_date": "2026-06-30",
            "volume": 100000,
            "liquidity": None,
            "current_yes_price": 0.30,
            "raw_json": "{}",
        }
        result = normalize_market(raw, "kalshi")
        assert result["id"] == "kalshi:xyz789"
        assert result["platform"] == "kalshi"


class TestRulesHash:
    def test_deterministic(self):
        h1 = compute_rules_hash("some rules text")
        h2 = compute_rules_hash("some rules text")
        assert h1 == h2

    def test_different_content_different_hash(self):
        h1 = compute_rules_hash("rules version 1")
        h2 = compute_rules_hash("rules version 2")
        assert h1 != h2

    def test_whitespace_stripping(self):
        h1 = compute_rules_hash("  rules  ")
        h2 = compute_rules_hash("rules")
        assert h1 == h2


class TestDetectRuleChange:
    def test_no_change(self):
        rules = "some rules"
        h = compute_rules_hash(rules)
        assert detect_rule_change(rules, h) is False

    def test_change_detected(self):
        h = compute_rules_hash("old rules")
        assert detect_rule_change("new rules", h) is True

    def test_no_stored_hash(self):
        assert detect_rule_change("any rules", None) is True
