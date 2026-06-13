"""Fee model tests.

Recon (2026-06-09) confirmed fees are published per-market via Gamma's
feeSchedule: {exponent, rate, takerOnly, rebateRate}, with feesEnabled flag.
fee_per_share = rate * (p*(1-p))**exponent.
Cross-checked against the published schedule: general 0.05*0.25 = $1.25/100,
sports 0.03*0.25 = $0.75/100 at p=0.5. Category table is fallback only.
"""
import pytest

from pmtrader.core.fees import (
    CATEGORY_RATE,
    DEFAULT_RATE,
    FeeSchedule,
    maker_fee_per_share,
    maker_rebate_rate,
    order_taker_fee,
    taker_fee_per_share,
)

GENERAL = FeeSchedule(exponent=1.0, rate=0.05, taker_only=True, rebate_rate=0.25)
SPORTS = FeeSchedule(exponent=1.0, rate=0.03, taker_only=True, rebate_rate=0.25)


class TestScheduleFee:
    def test_general_peak_matches_published_125_per_100(self):
        assert taker_fee_per_share(0.5, schedule=GENERAL) == pytest.approx(0.0125)

    def test_sports_peak_matches_published_075_per_100(self):
        assert taker_fee_per_share(0.5, schedule=SPORTS) == pytest.approx(0.0075)

    def test_quadratic_profile(self):
        assert taker_fee_per_share(0.9, schedule=GENERAL) == pytest.approx(0.05 * 0.9 * 0.1)

    def test_fee_decreases_toward_extremes(self):
        assert taker_fee_per_share(0.99, schedule=GENERAL) < taker_fee_per_share(0.6, schedule=GENERAL)
        assert taker_fee_per_share(0.01, schedule=GENERAL) < taker_fee_per_share(0.4, schedule=GENERAL)

    def test_exponent_respected(self):
        sq = FeeSchedule(exponent=2.0, rate=0.05, taker_only=True, rebate_rate=0.25)
        assert taker_fee_per_share(0.5, schedule=sq) == pytest.approx(0.05 * 0.25**2)

    def test_fees_disabled_market_is_free(self):
        assert taker_fee_per_share(0.5, schedule=GENERAL, fees_enabled=False) == 0.0


class TestCategoryFallback:
    def test_crypto_fallback_matches_published_180_per_100(self):
        assert taker_fee_per_share(0.5, category="crypto") == pytest.approx(0.018)

    def test_geopolitics_free(self):
        assert taker_fee_per_share(0.5, category="geopolitics") == 0.0

    def test_unknown_category_uses_conservative_default(self):
        assert taker_fee_per_share(0.5, category="someweirdnewcategory") == pytest.approx(DEFAULT_RATE * 0.25)

    def test_category_case_insensitive(self):
        assert taker_fee_per_share(0.5, category="Crypto") == pytest.approx(0.018)

    def test_schedule_wins_over_category(self):
        assert taker_fee_per_share(0.5, schedule=SPORTS, category="crypto") == pytest.approx(0.0075)

    def test_no_schedule_no_category_uses_default(self):
        assert taker_fee_per_share(0.5) == pytest.approx(DEFAULT_RATE * 0.25)


class TestMakerSide:
    def test_maker_fee_zero_when_taker_only(self):
        assert maker_fee_per_share(0.5, schedule=GENERAL) == 0.0

    def test_maker_fee_charged_when_not_taker_only(self):
        both = FeeSchedule(exponent=1.0, rate=0.05, taker_only=False, rebate_rate=0.25)
        assert maker_fee_per_share(0.5, schedule=both) == pytest.approx(0.0125)

    def test_maker_fee_zero_for_category_fallback(self):
        for cat in CATEGORY_RATE:
            assert maker_fee_per_share(0.5, category=cat) == 0.0

    def test_rebate_rate_exposed(self):
        assert maker_rebate_rate(GENERAL) == 0.25
        assert maker_rebate_rate(None) == 0.0


class TestOrderFee:
    def test_order_fee_total(self):
        assert order_taker_fee(price=0.5, size=200, schedule=SPORTS) == pytest.approx(200 * 0.0075)

    def test_order_fee_off_peak(self):
        expected = 100 * 0.05 * 0.8 * 0.2
        assert order_taker_fee(price=0.8, size=100, schedule=GENERAL) == pytest.approx(expected)
