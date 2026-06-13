"""Unit tests for price extraction (works on both live responses and stored
raw_payload — same field names per venue)."""
import pytest

from tool.api.pricing import extract_price


def test_polymarket_from_outcome_prices():
    m = {"outcomes": '["Yes", "No"]', "outcomePrices": '["0.265", "0.735"]'}
    assert extract_price("polymarket", m) == {"yes": 0.265, "no": 0.735}


def test_polymarket_outcomes_as_lists():
    m = {"outcomes": ["No", "Yes"], "outcomePrices": ["0.7", "0.3"]}
    assert extract_price("polymarket", m) == {"yes": 0.3, "no": 0.7}


def test_polymarket_fallback_to_best_bid_ask():
    m = {"bestBid": 0.25, "bestAsk": 0.27}
    out = extract_price("polymarket", m)
    assert out["yes"] == pytest.approx(0.26)
    assert out["no"] == pytest.approx(0.74)


def test_kalshi_midpoint():
    m = {"yes_bid_dollars": "0.3080", "yes_ask_dollars": "0.3190"}
    out = extract_price("kalshi", m)
    assert out["yes"] == pytest.approx(0.3135)
    assert out["no"] == pytest.approx(0.6865)


def test_kalshi_fallback_to_last_price():
    m = {"last_price_dollars": "0.42"}
    assert extract_price("kalshi", m) == {"yes": 0.42, "no": 0.58}


def test_missing_prices_returns_none():
    assert extract_price("polymarket", {}) is None
    assert extract_price("kalshi", {}) is None


def test_unsupported_venue_returns_none():
    assert extract_price("gemini", {"yes_bid_dollars": "0.5"}) is None
