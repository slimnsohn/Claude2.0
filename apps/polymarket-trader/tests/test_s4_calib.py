"""S4 calibration harvester: bucket table math + whitelist-gated strategy."""
import pytest

from pmtrader.core.fees import FeeSchedule
from pmtrader.core.models import Level, Market, OrderBook, Side
from pmtrader.strategies.base import StrategyContext
from pmtrader.strategies.s4_calib import (
    Bucket,
    S4Calib,
    calibration_table,
    wilson_lower,
)

FREE = FeeSchedule(exponent=1, rate=0.0, taker_only=True, rebate_rate=0.0)


def mk_market(cid="m1", category="general", end_date="2026-12-31T00:00:00Z"):
    return Market(condition_id=cid, question="Q?", category=category,
                  token_id_yes=f"{cid}-yes", token_id_no=f"{cid}-no",
                  neg_risk=False, end_date=end_date, fee_schedule=FREE, active=True)


def mk_books(market, yes_bid, yes_ask, depth=1000.0, ts=100.0):
    def book(token, bid, ask):
        return OrderBook(token_id=token, ts=ts,
                         bids=[Level(price=bid, size=depth)],
                         asks=[Level(price=ask, size=depth)])
    return {market.token_id_yes: book(market.token_id_yes, yes_bid, yes_ask),
            market.token_id_no: book(market.token_id_no, 1 - yes_ask, 1 - yes_bid)}


class TestWilson:
    def test_wilson_lower_below_point_estimate(self):
        assert wilson_lower(95, 100) < 0.95

    def test_wilson_tightens_with_n(self):
        assert wilson_lower(95, 100) < wilson_lower(950, 1000)

    def test_wilson_zero_n(self):
        assert wilson_lower(0, 0) == 0.0


class TestCalibrationTable:
    def make_rows(self):
        # rows: (category, price, days_to_res, won)
        # 95c general bucket: 58 wins / 60 -> hit rate 0.967 > price 0.95
        rows = [("general", 0.95, 3.0, True)] * 58 + [("general", 0.95, 3.0, False)] * 2
        # 30c longshot bucket: wins only 20% -> overpriced longshots
        rows += [("general", 0.30, 3.0, True)] * 12 + [("general", 0.30, 3.0, False)] * 48
        return rows

    def test_buckets_aggregate(self):
        table = calibration_table(self.make_rows())
        b95 = table[Bucket(category="general", price_decile=9, dtr_band="0-7d")]
        assert b95.n == 60 and b95.wins == 58
        assert b95.hit_rate == pytest.approx(58 / 60)

    def test_wilson_bounds_present(self):
        table = calibration_table(self.make_rows())
        b = table[Bucket(category="general", price_decile=9, dtr_band="0-7d")]
        assert 0 < b.wilson_lo < b.hit_rate

    def test_dtr_bands(self):
        rows = [("general", 0.5, 1.0, True), ("general", 0.5, 20.0, True),
                ("general", 0.5, 100.0, False)]
        table = calibration_table(rows)
        assert Bucket("general", 5, "0-7d") in table
        assert Bucket("general", 5, "7-30d") in table
        assert Bucket("general", 5, "30d+") in table


class TestS4Strategy:
    def make_s4(self, whitelist=None):
        wl = whitelist if whitelist is not None else [
            {"category": "general", "price_decile": 9, "dtr_band": "0-7d",
             "wilson_lo": 0.962, "n": 500}]
        return S4Calib(params={"margin": 0.005}, whitelist=wl)

    def test_fires_in_whitelisted_bucket(self):
        s4 = self.make_s4()
        m = mk_market(end_date="2026-01-02T00:00:00Z")
        books = mk_books(m, 0.94, 0.95)
        ctx = StrategyContext(now=1767225600.0, budget=10_000)  # 2026-01-01
        intents = s4.on_books(m, books, ctx)
        # wilson_lo 0.962 - ask 0.95 - fee 0 = 0.012 > margin 0.005
        assert len(intents) == 1
        assert intents[0].side == Side.BUY
        assert intents[0].token_id == m.token_id_yes
        assert "bucket" in intents[0].reasoning

    def test_intent_carries_condition_and_event_ids(self):
        s4 = self.make_s4()
        m = mk_market(end_date="2026-01-02T00:00:00Z")
        m = m.model_copy(update={"event_id": "ev42"})
        ctx = StrategyContext(now=1767225600.0, budget=10_000)
        intents = s4.on_books(m, mk_books(m, 0.94, 0.95), ctx)
        assert intents[0].condition_id == m.condition_id
        assert intents[0].event_id == "ev42"  # event risk cap needs it

    def test_inert_with_empty_whitelist(self):
        s4 = self.make_s4(whitelist=[])
        m = mk_market(end_date="2026-01-02T00:00:00Z")
        ctx = StrategyContext(now=1767225600.0, budget=10_000)
        assert s4.on_books(m, mk_books(m, 0.94, 0.95), ctx) == []

    def test_no_fire_outside_bucket_price(self):
        s4 = self.make_s4()
        m = mk_market(end_date="2026-01-02T00:00:00Z")
        ctx = StrategyContext(now=1767225600.0, budget=10_000)
        assert s4.on_books(m, mk_books(m, 0.84, 0.85), ctx) == []  # decile 8

    def test_no_fire_when_edge_below_margin(self):
        wl = [{"category": "general", "price_decile": 9, "dtr_band": "0-7d",
               "wilson_lo": 0.953, "n": 500}]
        s4 = self.make_s4(whitelist=wl)
        m = mk_market(end_date="2026-01-02T00:00:00Z")
        ctx = StrategyContext(now=1767225600.0, budget=10_000)
        # 0.953 - 0.95 = 0.003 < margin 0.005
        assert s4.on_books(m, mk_books(m, 0.94, 0.95), ctx) == []

    def test_per_market_cap_respected(self):
        s4 = self.make_s4()
        m = mk_market(end_date="2026-01-02T00:00:00Z")
        ctx = StrategyContext(now=1767225600.0, budget=10_000)
        intents = s4.on_books(m, mk_books(m, 0.94, 0.95), ctx)
        # max_market_notional default 200 -> at 0.95, ~210 shares
        assert intents[0].size * intents[0].price <= s4.params["max_market_notional"] + 1

    def test_one_shot_per_market(self):
        s4 = self.make_s4()
        m = mk_market(end_date="2026-01-02T00:00:00Z")
        ctx = StrategyContext(now=1767225600.0, budget=10_000)
        assert s4.on_books(m, mk_books(m, 0.94, 0.95), ctx)
        assert s4.on_books(m, mk_books(m, 0.94, 0.95), ctx) == []
