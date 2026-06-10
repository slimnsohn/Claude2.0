"""Risk manager: one approving + one vetoing test per rule. 100% branch required."""
import pytest

from pmtrader.core.fees import FeeSchedule
from pmtrader.core.models import Intent, Level, Market, OrderBook, Position, Side
from pmtrader.risk import PortfolioSnapshot, RiskManager, Veto

FREE = FeeSchedule(exponent=1, rate=0.0, taker_only=True, rebate_rate=0.0)
GENERAL = FeeSchedule(exponent=1, rate=0.05, taker_only=True, rebate_rate=0.25)


def mk_market(cid="m1", schedule=FREE, end_date="2026-12-31T00:00:00Z"):
    return Market(condition_id=cid, question="Q?", category="general",
                  token_id_yes=f"{cid}-yes", token_id_no=f"{cid}-no",
                  neg_risk=False, end_date=end_date, fee_schedule=schedule,
                  active=True, event_id="ev1")


def mk_book(token="m1-yes", bid=0.39, ask=0.41, depth=1000.0, ts=100.0):
    return OrderBook(token_id=token, ts=ts,
                     bids=[Level(price=bid, size=depth)],
                     asks=[Level(price=ask, size=depth)])


def mk_intent(**overrides):
    base = dict(strategy="s1", token_id="m1-yes", side=Side.BUY, price=0.40,
                size=50.0, expected_edge=0.02, reasoning="test",
                condition_id="m1", event_id="ev1")
    base.update(overrides)
    return Intent(**base)


def mk_snapshot(**overrides):
    m = mk_market()
    base = dict(
        now=100.0, cash=1000.0, equity=1000.0, day_pnl=0.0,
        positions={}, marks={}, books={"m1-yes": mk_book()},
        markets={"m1": m}, halted=False,
    )
    base.update(overrides)
    return PortfolioSnapshot(**base)


@pytest.fixture
def risk():
    return RiskManager()


class TestMissingConditionId:
    def test_veto_entry_without_condition_id(self, risk):
        # exposure caps key off condition_id; an entry without one would
        # silently bypass the per-market cap, so it is vetoed outright
        decision = risk.check(mk_intent(condition_id=None), mk_snapshot())
        assert isinstance(decision, Veto)
        assert decision.rule == "missing_condition_id"

    def test_reduce_sell_without_condition_id_allowed(self, risk):
        snap = mk_snapshot(positions={"m1-yes": Position(
            token_id="m1-yes", size=100.0, avg_cost=0.40, condition_id="m1")},
            marks={"m1-yes": 0.40})
        decision = risk.check(
            mk_intent(side=Side.SELL, size=50.0, condition_id=None), snap)
        assert not isinstance(decision, Veto)


class TestEvRule:
    def test_veto_negative_ev_after_fees(self, risk):
        m = mk_market(schedule=GENERAL)
        snap = mk_snapshot(markets={"m1": m})
        # edge claimed 0.001 but fee at 0.40 = 0.05*0.4*0.6 = 0.012
        decision = risk.check(mk_intent(expected_edge=0.001), snap)
        assert isinstance(decision, Veto) and decision.rule == "ev_after_fees"

    def test_pass_when_edge_clears_fees(self, risk):
        m = mk_market(schedule=GENERAL)
        snap = mk_snapshot(markets={"m1": m})
        decision = risk.check(mk_intent(expected_edge=0.02), snap)
        assert not isinstance(decision, Veto)

    def test_maker_intent_pays_no_taker_fee(self, risk):
        m = mk_market(schedule=GENERAL)
        snap = mk_snapshot(markets={"m1": m})
        decision = risk.check(mk_intent(expected_edge=0.001, post_only=True), snap)
        assert not isinstance(decision, Veto)


class TestExposureCaps:
    def test_veto_market_exposure(self, risk):
        snap = mk_snapshot(positions={"m1-yes": Position(
            token_id="m1-yes", size=120.0, avg_cost=0.40, condition_id="m1")},
            marks={"m1-yes": 0.40})
        # existing 48 + new 20 = 68 > 5% of 1000
        decision = risk.check(mk_intent(size=50.0), snap)
        assert isinstance(decision, Veto) and decision.rule == "max_market_frac"

    def test_market_exposure_passes_below_cap(self, risk):
        decision = risk.check(mk_intent(size=50.0), mk_snapshot())  # 20 < 50
        assert not isinstance(decision, Veto)

    def test_veto_event_exposure(self, risk):
        m2 = mk_market(cid="m2")
        snap = mk_snapshot(
            markets={"m1": mk_market(), "m2": m2},
            positions={"m2-yes": Position(token_id="m2-yes", size=250.0,
                                          avg_cost=0.38, condition_id="m2",
                                          event_id="ev1")},
            marks={"m2-yes": 0.38})
        # event ev1: 95 existing + 20 new = 115 > 10% of 1000
        decision = risk.check(mk_intent(), snap)
        assert isinstance(decision, Veto) and decision.rule == "max_event_frac"

    def test_veto_total_at_risk(self, risk):
        snap = mk_snapshot(cash=150.0, positions={"x-yes": Position(
            token_id="x-yes", size=2200.0, avg_cost=0.39, condition_id="x")},
            marks={"x-yes": 0.39})
        # at risk: 858 marks + 20 new = 878 > 80% of equity (1008)? equity=cash+marks=1008
        # 80% of 1008 = 806.4 -> 878 > 806.4 veto
        decision = risk.check(mk_intent(), snap)
        assert isinstance(decision, Veto) and decision.rule == "max_at_risk_frac"


class TestHaltAndStale:
    def test_halt_vetoes_everything(self, risk):
        decision = risk.check(mk_intent(), mk_snapshot(halted=True))
        assert isinstance(decision, Veto) and decision.rule == "halted"

    def test_daily_loss_halts(self, risk):
        decision = risk.check(mk_intent(), mk_snapshot(day_pnl=-101.0))
        assert isinstance(decision, Veto) and decision.rule == "daily_loss_halt"

    def test_stale_book_vetoed(self, risk):
        snap = mk_snapshot(books={"m1-yes": mk_book(ts=80.0)}, now=100.0)
        decision = risk.check(mk_intent(), snap)
        assert isinstance(decision, Veto) and decision.rule == "stale_book"

    def test_missing_book_vetoed(self, risk):
        decision = risk.check(mk_intent(), mk_snapshot(books={}))
        assert isinstance(decision, Veto) and decision.rule == "stale_book"


class TestDepthAndBlackout:
    def test_marketable_buy_downsized_to_depth_cap(self, risk):
        snap = mk_snapshot(books={"m1-yes": mk_book(depth=100.0)})
        # marketable buy at the ask: 50 requested, 25% of 100 displayed = 25
        decision = risk.check(mk_intent(price=0.41, size=50.0), snap)
        assert not isinstance(decision, Veto)
        assert decision.size == pytest.approx(25.0)

    def test_tiny_depth_vetoed(self, risk):
        snap = mk_snapshot(books={"m1-yes": mk_book(depth=2.0)})
        decision = risk.check(mk_intent(price=0.41, size=50.0), snap)
        assert isinstance(decision, Veto) and decision.rule == "max_book_frac"

    def test_grouped_intent_skips_kelly(self, risk):
        # arb leg with tiny per-leg edge would be kelly-vetoed if ungrouped
        decision = risk.check(
            mk_intent(size=20.0, expected_edge=0.0003, group_id="g1"),
            mk_snapshot())
        assert not isinstance(decision, Veto)
        assert decision.size == pytest.approx(20.0)

    def test_resting_buy_not_depth_limited(self, risk):
        snap = mk_snapshot(books={"m1-yes": mk_book(depth=100.0)})
        decision = risk.check(mk_intent(price=0.40, size=50.0), snap)  # rests below ask
        assert not isinstance(decision, Veto)

    def test_sell_side_downsized_to_bid_depth(self, risk):
        snap = mk_snapshot(books={"m1-yes": mk_book(depth=100.0)},
                           positions={"m1-yes": Position(
                               token_id="m1-yes", size=30.0, avg_cost=0.4,
                               condition_id="m1")},
                           marks={"m1-yes": 0.40})
        # marketable sell into the bid: 30 requested, cap 25
        decision = risk.check(mk_intent(side=Side.SELL, price=0.39, size=30.0), snap)
        assert not isinstance(decision, Veto)
        assert decision.size == pytest.approx(25.0)

    def test_veto_resolution_blackout(self, risk):
        m = mk_market(end_date="2026-12-31T00:00:00Z")
        end_ts = 1798675200.0  # 2026-12-31T00:00:00Z
        snap = mk_snapshot(now=end_ts - 60, markets={"m1": m},
                           books={"m1-yes": mk_book(ts=end_ts - 60)})
        decision = risk.check(mk_intent(), snap)
        assert isinstance(decision, Veto) and decision.rule == "resolution_blackout"

    def test_s1_unwind_exempt_from_blackout(self, risk):
        end_ts = 1798675200.0
        snap = mk_snapshot(now=end_ts - 60,
                           books={"m1-yes": mk_book(ts=end_ts - 60)},
                           positions={"m1-yes": Position(
                               token_id="m1-yes", size=100.0, avg_cost=0.4,
                               condition_id="m1")},
                           marks={"m1-yes": 0.40})
        decision = risk.check(
            mk_intent(strategy="s1_arb", side=Side.SELL, size=10.0), snap)
        assert not isinstance(decision, Veto)


class TestKellySizing:
    def test_kelly_downsizes_not_upsizes(self, risk):
        # tiny edge -> kelly cap small; approved size = min(requested, kelly)
        approved = risk.check(mk_intent(size=50.0, expected_edge=0.001), mk_snapshot())
        # kelly: f* = 0.001/(0.4*0.6) = 0.004166 * 1000 * 0.25 = 1.04 dollars -> ~2 shares
        assert not isinstance(approved, Veto)
        assert approved.size < 50.0

    def test_kelly_never_increases(self, risk):
        approved = risk.check(mk_intent(size=10.0, expected_edge=0.10), mk_snapshot())
        assert not isinstance(approved, Veto)
        assert approved.size <= 10.0

    def test_sell_of_held_position_not_kelly_limited(self, risk):
        snap = mk_snapshot(positions={"m1-yes": Position(
            token_id="m1-yes", size=20.0, avg_cost=0.40, condition_id="m1")},
            marks={"m1-yes": 0.40})
        approved = risk.check(
            mk_intent(side=Side.SELL, size=20.0, expected_edge=0.0), snap)
        assert not isinstance(approved, Veto)
        assert approved.size == 20.0


class TestBranchEdges:
    def test_unknown_market_skips_blackout_and_fee(self, risk):
        snap = mk_snapshot(markets={})
        decision = risk.check(mk_intent(condition_id="nope"), snap)
        assert not isinstance(decision, Veto)

    def test_post_only_marketable_skips_depth_rule(self, risk):
        snap = mk_snapshot(books={"m1-yes": mk_book(depth=100.0)})
        decision = risk.check(
            mk_intent(price=0.41, size=50.0, post_only=True), snap)
        assert not isinstance(decision, Veto)

    def test_no_event_id_skips_event_cap(self, risk):
        decision = risk.check(mk_intent(event_id=None), mk_snapshot())
        assert not isinstance(decision, Veto)

    def test_marketable_buy_within_depth_approved(self, risk):
        snap = mk_snapshot(books={"m1-yes": mk_book(depth=1000.0)})
        decision = risk.check(mk_intent(price=0.41, size=50.0), snap)
        assert not isinstance(decision, Veto)

    def test_buy_into_empty_ask_book_rests(self, risk):
        empty_asks = OrderBook(token_id="m1-yes", ts=100.0,
                               bids=[Level(price=0.39, size=1000.0)], asks=[])
        snap = mk_snapshot(books={"m1-yes": empty_asks})
        decision = risk.check(mk_intent(price=0.40, size=20.0), snap)
        assert not isinstance(decision, Veto)

    def test_sell_into_empty_bid_book_rests(self, risk):
        empty_bids = OrderBook(token_id="m1-yes", ts=100.0, bids=[],
                               asks=[Level(price=0.41, size=1000.0)])
        snap = mk_snapshot(books={"m1-yes": empty_bids},
                           positions={"m1-yes": Position(
                               token_id="m1-yes", size=30.0, avg_cost=0.4,
                               condition_id="m1")},
                           marks={"m1-yes": 0.40})
        decision = risk.check(mk_intent(side=Side.SELL, price=0.39, size=30.0), snap)
        assert not isinstance(decision, Veto)

    def test_kelly_below_one_share_vetoed(self, risk):
        # edge so tiny that quarter-kelly sizes below a single share
        decision = risk.check(mk_intent(size=2.0, expected_edge=0.0003),
                              mk_snapshot())
        assert isinstance(decision, Veto) and decision.rule == "kelly_zero"


class TestApprovalShape:
    def test_approval_carries_reasoning(self, risk):
        approved = risk.check(mk_intent(), mk_snapshot())
        assert not isinstance(approved, Veto)
        assert approved.size > 0
        assert "approved" in approved.detail

    def test_sell_more_than_held_vetoed(self, risk):
        decision = risk.check(mk_intent(side=Side.SELL, size=10.0), mk_snapshot())
        assert isinstance(decision, Veto) and decision.rule == "short_sale"
