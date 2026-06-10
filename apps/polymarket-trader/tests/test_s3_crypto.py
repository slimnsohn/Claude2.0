"""S3 crypto fair value: binary-option pricing, vol estimation, no-trade band."""
import math

import pytest

from pmtrader.core.fees import FeeSchedule
from pmtrader.core.models import Level, Market, OrderBook, Side
from pmtrader.strategies.base import StrategyContext
from pmtrader.strategies.s3_crypto import (
    S3Crypto,
    ewma_vol_annualized,
    fair_value,
    parse_strike,
)

CRYPTO = FeeSchedule(exponent=1, rate=0.072, taker_only=True, rebate_rate=0.20)


def phi(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


class TestFairValue:
    def test_atm_is_half(self):
        assert fair_value(spot=100_000, strike=100_000, sigma_ann=0.5,
                          tau_years=1 / 365) == pytest.approx(0.5, abs=1e-9)

    def test_monotonic_in_spot(self):
        vals = [fair_value(s, 100_000, 0.5, 7 / 365)
                for s in (90_000, 100_000, 110_000)]
        assert vals[0] < vals[1] < vals[2]

    def test_known_case(self):
        # S=105k, K=100k, sigma=60%, tau=7/365: d = ln(1.05)/(0.6*sqrt(7/365))
        d = math.log(1.05) / (0.6 * math.sqrt(7 / 365))
        assert fair_value(105_000, 100_000, 0.6, 7 / 365) == \
            pytest.approx(phi(d), abs=1e-6)

    def test_zero_tau_is_indicator(self):
        assert fair_value(105_000, 100_000, 0.6, 0.0) == 1.0
        assert fair_value(95_000, 100_000, 0.6, 0.0) == 0.0


class TestVolEstimator:
    def test_matches_hand_calc(self):
        closes = [(60.0 * i, p) for i, p in
                  enumerate([100.0, 101.0, 100.5, 101.5, 101.0, 102.0])]
        lam = 0.94
        rets = [math.log(closes[i][1] / closes[i - 1][1])
                for i in range(1, len(closes))]
        var = rets[0] ** 2
        for r in rets[1:]:
            var = lam * var + (1 - lam) * r * r
        minutes_per_year = 365 * 24 * 60
        expected = math.sqrt(var * minutes_per_year)
        assert ewma_vol_annualized(closes, lam=lam) == pytest.approx(expected)

    def test_too_few_points_returns_none(self):
        assert ewma_vol_annualized([(0.0, 100.0)]) is None


class TestParseStrike:
    def test_above_with_commas(self):
        strike, direction = parse_strike("Will Bitcoin be above $112,000 on June 13?")
        assert strike == 112_000.0 and direction == "above"

    def test_reach(self):
        strike, direction = parse_strike("Will Ethereum reach $4,000 by July 1?")
        assert strike == 4_000.0 and direction == "above"

    def test_below(self):
        strike, direction = parse_strike("Will Bitcoin dip below $90,000 in June?")
        assert strike == 90_000.0 and direction == "below"

    def test_unparseable(self):
        assert parse_strike("Bitcoin Up or Down - June 10, 3PM ET") is None


def mk_market(question="Will Bitcoin be above $110,000 on June 13?",
              end_date="2026-06-13T12:00:00Z"):
    return Market(condition_id="c1", question=question, category="crypto",
                  token_id_yes="c1-yes", token_id_no="c1-no", neg_risk=False,
                  end_date=end_date, fee_schedule=CRYPTO, active=True)


def mk_books(market, bid, ask, depth=2000.0, ts=1_000_000.0):
    return {market.token_id_yes: OrderBook(
        token_id=market.token_id_yes, ts=ts,
        bids=[Level(price=bid, size=depth)],
        asks=[Level(price=ask, size=depth)]),
        market.token_id_no: OrderBook(
        token_id=market.token_id_no, ts=ts,
        bids=[Level(price=1 - ask, size=depth)],
        asks=[Level(price=1 - bid, size=depth)])}


NOW = 1781100000.0  # 2026-06-10-ish; end 2026-06-13T12:00Z = 1781438400


def primed_s3(spot=100_000.0, vol=0.5, **params):
    s3 = S3Crypto(params=dict({"margin": 0.01}, **params))
    s3.update_spot("BTC", spot, vol_annualized=vol)
    return s3


class TestS3Trading:
    def test_no_trade_inside_band(self):
        s3 = primed_s3()
        m = mk_market()  # strike 110k, spot 100k, 3.4d, vol 50%
        # fair value ~ Phi(ln(100/110)/(0.5*sqrt(3.9/365))) ~ very low ~0.03
        # market priced near fair -> no trade
        books = mk_books(m, 0.02, 0.05)
        assert s3.on_books(m, books, StrategyContext(now=NOW, budget=5000)) == []

    def test_trade_fires_on_big_divergence_with_reasoning(self):
        s3 = primed_s3()
        m = mk_market()
        # market says 35c for something the model prices ~3c -> buy NO via
        # sell-side? we can't short; the trade is BUY NO at (1-0.36)=0.64?
        # NO fair = 0.97; NO ask = 0.65 -> huge edge -> buy NO
        books = mk_books(m, 0.35, 0.36)
        intents = s3.on_books(m, books, StrategyContext(now=NOW, budget=5000))
        assert len(intents) == 1
        i = intents[0]
        assert i.token_id == m.token_id_no and i.side == Side.BUY
        assert "fair=" in i.reasoning and "sigma=" in i.reasoning
        assert i.expected_edge > 0

    def test_buy_yes_when_market_underprices(self):
        s3 = primed_s3(spot=120_000.0)
        m = mk_market()  # strike 110k, spot 120k -> fair ~ 0.96
        books = mk_books(m, 0.60, 0.62)
        intents = s3.on_books(m, books, StrategyContext(now=NOW, budget=5000))
        assert len(intents) == 1
        assert intents[0].token_id == m.token_id_yes
        assert intents[0].side == Side.BUY

    def test_no_spot_data_no_trade(self):
        s3 = S3Crypto(params={"margin": 0.01})
        m = mk_market()
        assert s3.on_books(m, mk_books(m, 0.35, 0.36),
                           StrategyContext(now=NOW, budget=5000)) == []

    def test_unparseable_market_skipped(self):
        s3 = primed_s3()
        m = mk_market(question="Bitcoin Up or Down - June 10, 3PM ET")
        assert s3.on_books(m, mk_books(m, 0.35, 0.36),
                           StrategyContext(now=NOW, budget=5000)) == []

    def test_vol_regime_guard_widens_band(self):
        calm = primed_s3()
        m = mk_market()
        books = mk_books(m, 0.10, 0.12)  # moderate divergence (fair ~0.03)
        base = calm.on_books(m, books, StrategyContext(now=NOW, budget=5000))
        assert len(base) == 1  # trades in calm regime

        shaky = primed_s3()
        # feed unstable vol estimates -> vol-of-vol guard multiplies margin
        for k, v in enumerate([0.3, 0.8, 0.4, 0.9, 0.35, 0.95]):
            shaky.update_spot("BTC", 100_000.0, vol_annualized=v)
        result = shaky.on_books(m, books, StrategyContext(now=NOW, budget=5000))
        assert result == []  # same divergence suppressed in unstable regime

    def test_prefers_maker_when_spread_wide(self):
        s3 = primed_s3(spot=120_000.0)
        m = mk_market()
        # wide spread: post inside instead of paying it
        books = mk_books(m, 0.55, 0.70)
        intents = s3.on_books(m, books, StrategyContext(now=NOW, budget=5000))
        assert len(intents) == 1
        i = intents[0]
        assert i.post_only is True
        assert i.price < 0.70  # posted inside the spread, not taking

    def test_one_position_per_market(self):
        s3 = primed_s3(spot=120_000.0)
        m = mk_market()
        books = mk_books(m, 0.60, 0.62)
        assert s3.on_books(m, books, StrategyContext(now=NOW, budget=5000))
        assert s3.on_books(m, books, StrategyContext(now=NOW, budget=5000)) == []

    def test_expired_market_skipped(self):
        s3 = primed_s3()
        m = mk_market(end_date="2026-06-01T00:00:00Z")  # already past
        assert s3.on_books(m, mk_books(m, 0.35, 0.36),
                           StrategyContext(now=NOW, budget=5000)) == []
