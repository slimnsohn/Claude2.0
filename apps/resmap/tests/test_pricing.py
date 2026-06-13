"""Unit tests for price + fee extraction (works on both live responses and
stored raw_payload — same field names per venue)."""
import math

import pytest

from tool.api.pricing import extract_fees, extract_price


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


# ── fees ─────────────────────────────────────────────────────────────────────

def test_kalshi_fee_formula_rounded_up_to_cent():
    f = extract_fees("kalshi", {}, 0.5, 0.5)
    # 0.07 * 0.5 * 0.5 = 0.0175 → rounds up to 0.02
    assert f["yes_fee"] == 0.02 and f["no_fee"] == 0.02


def test_kalshi_fee_small_price_still_rounds_to_cent():
    f = extract_fees("kalshi", {}, 0.07, 0.93)
    # 0.07*0.07*0.93 = 0.00456 → ceil to 0.01
    assert f["yes_fee"] == 0.01


def test_polymarket_fee_from_schedule():
    m = {"feesEnabled": True, "feeSchedule": {"rate": 0.04, "exponent": 1}}
    f = extract_fees("polymarket", m, 0.5, 0.5)
    assert f["yes_fee"] == pytest.approx(0.5 * 0.04 * 0.25)   # 0.005/share


def test_polymarket_fee_free_when_disabled():
    assert extract_fees("polymarket", {"feesEnabled": False}, 0.5, 0.5)["yes_fee"] == 0.0
    assert extract_fees("polymarket", {}, 0.5, 0.5)["no_fee"] == 0.0


def test_settlement_is_never_charged():
    # the formula returns 0 at the resolution prices on both venues
    assert extract_fees("kalshi", {}, 1.0, 0.0)["yes_fee"] == 0.0
    m = {"feesEnabled": True, "feeSchedule": {"rate": 0.04, "exponent": 1}}
    assert extract_fees("polymarket", m, 1.0, 0.0)["yes_fee"] == 0.0
