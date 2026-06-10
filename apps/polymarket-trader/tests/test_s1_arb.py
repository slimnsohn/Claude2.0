"""S1 structural arb scanner — golden book fixtures, exact intent assertions."""
import pytest

from pmtrader.core.fees import FeeSchedule
from pmtrader.core.models import Level, Market, OrderBook, Side
from pmtrader.datalayer.gamma import Event
from pmtrader.strategies.base import StrategyContext
from pmtrader.strategies.s1_arb import S1Arb

FREE = FeeSchedule(exponent=1, rate=0.0, taker_only=True, rebate_rate=0.0)
CRYPTO = FeeSchedule(exponent=1, rate=0.072, taker_only=True, rebate_rate=0.20)


def mk_market(cid="m1", schedule=FREE, category="geopolitics"):
    return Market(condition_id=cid, question="Q?", category=category,
                  token_id_yes=f"{cid}-yes", token_id_no=f"{cid}-no",
                  neg_risk=False, end_date="2026-12-31T00:00:00Z",
                  fee_schedule=schedule, active=True)


def mk_books(market, yes_ask, no_ask, depth=500.0, ts=100.0):
    def book(token, ask):
        return OrderBook(token_id=token, ts=ts,
                         bids=[Level(price=max(0.001, ask - 0.02), size=depth)],
                         asks=[Level(price=ask, size=depth)])
    return {market.token_id_yes: book(market.token_id_yes, yes_ask),
            market.token_id_no: book(market.token_id_no, no_ask)}


def ctx(now=100.0, budget=10_000.0):
    return StrategyContext(now=now, cash=budget, budget=budget)


@pytest.fixture
def s1():
    return S1Arb()


class TestBinaryPairArb:
    def test_fires_on_cheap_pair(self, s1):
        m = mk_market()
        intents = s1.on_books(m, mk_books(m, 0.46, 0.50), ctx())
        assert len(intents) == 2
        assert all(i.side == Side.BUY for i in intents)
        assert {i.token_id for i in intents} == {m.token_id_yes, m.token_id_no}
        assert intents[0].size == intents[1].size  # matched legs
        assert intents[0].group_id == intents[1].group_id
        assert intents[0].group_id is not None
        assert "sum=0.9600" in intents[0].reasoning

    def test_legs_carry_condition_and_event_ids(self, s1):
        m = mk_market()
        m = m.model_copy(update={"event_id": "ev42"})
        intents = s1.on_books(m, mk_books(m, 0.46, 0.50), ctx())
        assert all(i.condition_id == m.condition_id for i in intents)
        assert all(i.event_id == "ev42" for i in intents)  # event risk cap needs it

    def test_edge_must_clear_epsilon(self, s1):
        m = mk_market()
        # sum = 0.998, epsilon default 0.005 -> no fire
        assert s1.on_books(m, mk_books(m, 0.498, 0.50), ctx()) == []

    def test_respects_fees_in_taxed_category(self, s1):
        m = mk_market(schedule=CRYPTO, category="crypto")
        # sum 0.985: gross edge 0.015 but crypto fees ~0.018/share at midrange
        assert s1.on_books(m, mk_books(m, 0.485, 0.50), ctx()) == []

    def test_taxed_category_fires_when_edge_clears_fees(self, s1):
        m = mk_market(schedule=CRYPTO, category="crypto")
        # sum 0.90: gross 0.10 >> fees + eps
        intents = s1.on_books(m, mk_books(m, 0.40, 0.50), ctx())
        assert len(intents) == 2

    def test_sizes_to_book_depth(self, s1):
        m = mk_market()
        intents = s1.on_books(m, mk_books(m, 0.46, 0.50, depth=120.0), ctx())
        assert intents[0].size <= 120.0

    def test_sizes_to_budget(self, s1):
        m = mk_market()
        intents = s1.on_books(m, mk_books(m, 0.46, 0.50), ctx(budget=48.0))
        # 0.96 per pair -> at most 50 pairs
        assert intents[0].size <= 50.0

    def test_no_fire_when_sum_above_one(self, s1):
        m = mk_market()
        assert s1.on_books(m, mk_books(m, 0.52, 0.50), ctx()) == []

    def test_no_refire_while_pending(self, s1):
        m = mk_market()
        first = s1.on_books(m, mk_books(m, 0.46, 0.50), ctx())
        assert len(first) == 2
        again = s1.on_books(m, mk_books(m, 0.46, 0.50), ctx())
        assert again == []  # already holding this market's arb

    def test_empty_book_no_crash(self, s1):
        m = mk_market()
        books = {m.token_id_yes: OrderBook(token_id=m.token_id_yes, ts=1, bids=[], asks=[]),
                 m.token_id_no: OrderBook(token_id=m.token_id_no, ts=1, bids=[], asks=[])}
        assert s1.on_books(m, books, ctx()) == []

    def test_min_size_respected(self, s1):
        m = mk_market()
        m = m.model_copy(update={"min_size": 5.0})
        # budget allows only 2 shares -> below min order size -> no fire
        assert s1.on_books(m, mk_books(m, 0.46, 0.50), ctx(budget=2.0)) == []


class TestNegRiskSetArb:
    def make_event(self, asks, schedule=FREE):
        markets, books = [], {}
        for i, ask in enumerate(asks):
            m = mk_market(cid=f"e{i}", schedule=schedule)
            m = m.model_copy(update={"neg_risk": True})
            markets.append(m)
            books.update(mk_books(m, ask, 1.0 - ask + 0.02))
        event = Event(id="ev1", title="Who wins?", neg_risk=True, markets=markets)
        return event, books

    def test_buy_all_yes_when_sum_cheap(self, s1):
        event, books = self.make_event([0.30, 0.30, 0.20, 0.13])  # sum 0.93
        intents = s1.on_event(event, books, ctx())
        assert len(intents) == 4
        assert all(i.side == Side.BUY for i in intents)
        assert len({i.group_id for i in intents}) == 1
        sizes = {i.size for i in intents}
        assert len(sizes) == 1  # equal legs

    def test_no_fire_when_edge_below_epsilon(self, s1):
        # sum 0.998 -> edge 0.002 < epsilon 0.005
        event, books = self.make_event([0.30, 0.30, 0.25, 0.148])
        assert s1.on_event(event, books, ctx()) == []

    def test_no_fire_for_non_negrisk_event(self, s1):
        event, books = self.make_event([0.30, 0.30, 0.20, 0.13])
        event = event.model_copy(update={"neg_risk": False})
        assert s1.on_event(event, books, ctx()) == []

    def test_missing_book_skips_event(self, s1):
        event, books = self.make_event([0.30, 0.30, 0.20, 0.13])
        books.pop(event.markets[0].token_id_yes)
        assert s1.on_event(event, books, ctx()) == []


class TestUnwindOnResolution:
    def test_fill_then_release_after_resolution(self, s1):
        m = mk_market()
        intents = s1.on_books(m, mk_books(m, 0.46, 0.50), ctx())
        assert intents
        s1.on_market_resolved(m.condition_id)
        again = s1.on_books(m, mk_books(m, 0.46, 0.50), ctx())
        assert len(again) == 2  # capital recycled, can fire again
