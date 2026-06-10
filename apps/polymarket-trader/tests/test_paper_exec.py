"""Paper execution backend — conservative fill simulation against live books."""
import pytest

from pmtrader.core.fees import FeeSchedule
from pmtrader.core.models import Intent, Level, Market, OrderBook, OrderStatus, Side
from pmtrader.datalayer.store import Store
from pmtrader.execution.paper import PaperExecution

GENERAL = FeeSchedule(exponent=1, rate=0.05, taker_only=True, rebate_rate=0.25)


def mk_market(cid="m1", schedule=GENERAL):
    return Market(condition_id=cid, question="Q?", category="general",
                  token_id_yes=f"{cid}-yes", token_id_no=f"{cid}-no",
                  neg_risk=False, end_date="2026-12-31T00:00:00Z",
                  fee_schedule=schedule, active=True)


def mk_book(token="m1-yes", ts=100.0, bids=None, asks=None):
    return OrderBook(
        token_id=token, ts=ts,
        bids=[Level(price=p, size=s) for p, s in (bids or [(0.39, 500)])],
        asks=[Level(price=p, size=s) for p, s in (asks or [(0.41, 500)])])


def mk_intent(price=0.41, size=100.0, side=Side.BUY, post_only=False, **kw):
    base = dict(strategy="s1", token_id="m1-yes", side=side, price=price,
                size=size, expected_edge=0.02, reasoning="test",
                condition_id="m1", post_only=post_only)
    base.update(kw)
    return Intent(**base)


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "p.db")
    yield s
    s.close()


@pytest.fixture
def paper(store):
    px = PaperExecution(store=store)
    px.register_market(mk_market())
    px.on_book(mk_book())
    return px


class TestTakerFills:
    def test_marketable_buy_fills_at_ask_with_fee(self, paper):
        order = paper.submit(mk_intent(), now=101.0)
        assert order.status == OrderStatus.FILLED
        assert order.avg_fill_price == pytest.approx(0.41)
        fills = paper.store.fills(token_id="m1-yes")
        # taker fee: 100 * 0.05 * 0.41 * 0.59 = 1.2095
        assert fills[0]["fee"] == pytest.approx(1.2095)
        assert fills[0]["maker"] == 0

    def test_buy_walks_depth(self, paper):
        paper.on_book(mk_book(asks=[(0.41, 60), (0.43, 100)]))
        order = paper.submit(mk_intent(price=0.43, size=100.0), now=101.0)
        assert order.status == OrderStatus.FILLED
        # 60 @ 0.41 + 40 @ 0.43 = 41.8 / 100
        assert order.avg_fill_price == pytest.approx(0.418)

    def test_partial_take_then_remainder_rests(self, paper):
        paper.on_book(mk_book(asks=[(0.41, 60)]))
        order = paper.submit(mk_intent(price=0.41, size=100.0), now=101.0)
        assert order.status == OrderStatus.PARTIALLY_FILLED
        assert order.filled_size == 60.0
        assert len(paper.open_orders()) == 1

    def test_non_marketable_rests(self, paper):
        order = paper.submit(mk_intent(price=0.38), now=101.0)
        assert order.status == OrderStatus.OPEN
        assert paper.open_orders() == [order]


class TestMakerFills:
    def test_resting_bid_fills_on_trade_through(self, paper):
        order = paper.submit(mk_intent(price=0.38), now=101.0)
        paper.on_trade("m1-yes", price=0.37, size=200.0, ts=102.0)
        assert order.status == OrderStatus.FILLED
        assert order.avg_fill_price == pytest.approx(0.38)  # our limit
        fills = paper.store.fills(token_id="m1-yes")
        assert fills[0]["maker"] == 1
        assert fills[0]["fee"] == 0.0

    def test_touch_without_trade_is_not_fill(self, paper):
        order = paper.submit(mk_intent(price=0.38), now=101.0)
        paper.on_book(mk_book(bids=[(0.38, 100)], asks=[(0.40, 100)]))
        assert order.status == OrderStatus.OPEN

    def test_partial_maker_fill_bounded_by_print_size(self, paper):
        order = paper.submit(mk_intent(price=0.38, size=100.0), now=101.0)
        paper.on_trade("m1-yes", price=0.37, size=30.0, ts=102.0)
        assert order.status == OrderStatus.PARTIALLY_FILLED
        assert order.filled_size == 30.0

    def test_trade_above_bid_no_fill(self, paper):
        order = paper.submit(mk_intent(price=0.38), now=101.0)
        paper.on_trade("m1-yes", price=0.39, size=500.0, ts=102.0)
        assert order.status == OrderStatus.OPEN

    def test_trade_at_bid_is_not_fill(self, paper):
        # queue priority: a print AT our limit does not mean we were filled
        order = paper.submit(mk_intent(price=0.38), now=101.0)
        paper.on_trade("m1-yes", price=0.38, size=500.0, ts=102.0)
        assert order.status == OrderStatus.OPEN

    def test_resting_ask_fills_on_trade_through(self, paper):
        # hold inventory first
        paper.submit(mk_intent(price=0.41, size=50.0), now=101.0)
        order = paper.submit(mk_intent(side=Side.SELL, price=0.45, size=50.0),
                             now=102.0)
        assert order.status == OrderStatus.OPEN
        paper.on_trade("m1-yes", price=0.46, size=80.0, ts=103.0)
        assert order.status == OrderStatus.FILLED

    def test_trade_at_ask_is_not_fill(self, paper):
        paper.submit(mk_intent(price=0.41, size=50.0), now=101.0)
        order = paper.submit(mk_intent(side=Side.SELL, price=0.45, size=50.0),
                             now=102.0)
        paper.on_trade("m1-yes", price=0.45, size=80.0, ts=103.0)
        assert order.status == OrderStatus.OPEN


class TestCancel:
    def test_cancel_removes_resting(self, paper):
        order = paper.submit(mk_intent(price=0.38), now=101.0)
        paper.cancel(order.order_id, now=102.0)
        assert order.status == OrderStatus.CANCELLED
        assert paper.open_orders() == []

    def test_cancel_all(self, paper):
        paper.submit(mk_intent(price=0.38), now=101.0)
        paper.submit(mk_intent(price=0.37, size=50.0), now=101.0)
        paper.cancel_all(now=102.0)
        assert paper.open_orders() == []

    def test_post_only_that_would_cross_is_rejected(self, paper):
        order = paper.submit(mk_intent(price=0.41, post_only=True), now=101.0)
        assert order.status == OrderStatus.REJECTED


class TestPositionsAndCash:
    def test_positions_track_fills(self, paper):
        paper.submit(mk_intent(size=100.0), now=101.0)
        pos = paper.positions()
        assert pos["m1-yes"].size == 100.0
        assert pos["m1-yes"].avg_cost == pytest.approx(0.41 + 1.2095 / 100)

    def test_cash_decreases_by_cost_plus_fee(self, paper):
        start = paper.cash
        paper.submit(mk_intent(size=100.0), now=101.0)
        assert paper.cash == pytest.approx(start - 41.0 - 1.2095)

    def test_sell_returns_cash_minus_fee(self, paper):
        paper.submit(mk_intent(size=100.0), now=101.0)
        cash_after_buy = paper.cash
        paper.on_book(mk_book(bids=[(0.45, 500)], asks=[(0.47, 500)]))
        paper.submit(mk_intent(side=Side.SELL, price=0.45, size=100.0), now=102.0)
        sell_fee = 100 * 0.05 * 0.45 * 0.55
        assert paper.cash == pytest.approx(cash_after_buy + 45.0 - sell_fee)

    def test_resolution_settles_positions(self, paper):
        paper.submit(mk_intent(size=100.0), now=101.0)
        cash_before = paper.cash
        paper.settle("m1", winning_token_id="m1-yes", ts=200.0)
        assert paper.cash == pytest.approx(cash_before + 100.0)
        assert paper.positions() == {}


class TestFillEvents:
    def test_fill_callback_fires(self, paper):
        events = []
        paper.on_fill_callbacks.append(lambda fill, order: events.append(fill))
        paper.submit(mk_intent(), now=101.0)
        assert len(events) == 1 and events[0].size == 100.0
