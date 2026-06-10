import pytest
from pydantic import ValidationError

from pmtrader.core.models import (
    Fill,
    Intent,
    Level,
    Market,
    Order,
    OrderBook,
    OrderStatus,
    Position,
    Side,
    TimeInForce,
)


def make_intent(**overrides):
    base = dict(
        strategy="s1", token_id="t1", side=Side.BUY, price=0.5, size=10.0,
        expected_edge=0.02, reasoning="test reasoning",
    )
    base.update(overrides)
    return Intent(**base)


class TestIntent:
    def test_intent_requires_reasoning(self):
        with pytest.raises(ValidationError):
            make_intent(reasoning="")

    def test_price_bounds(self):
        with pytest.raises(ValidationError):
            make_intent(price=1.2)
        with pytest.raises(ValidationError):
            make_intent(price=0.0)
        with pytest.raises(ValidationError):
            make_intent(price=1.0)

    def test_size_positive(self):
        with pytest.raises(ValidationError):
            make_intent(size=0)
        with pytest.raises(ValidationError):
            make_intent(size=-5)

    def test_defaults(self):
        i = make_intent()
        assert i.tif == TimeInForce.GTC
        assert i.post_only is False
        assert i.group_id is None


class TestOrderBook:
    def test_best_and_mid(self):
        book = OrderBook(
            token_id="t", ts=1.0,
            bids=[Level(price=0.48, size=100)], asks=[Level(price=0.52, size=80)],
        )
        assert book.best_bid == 0.48
        assert book.best_ask == 0.52
        assert book.mid == pytest.approx(0.50)

    def test_microprice_weights_by_size(self):
        book = OrderBook(
            token_id="t", ts=1.0,
            bids=[Level(price=0.40, size=300)], asks=[Level(price=0.60, size=100)],
        )
        # microprice = (bid*ask_size + ask*bid_size) / (bid_size + ask_size)
        expected = (0.40 * 100 + 0.60 * 300) / 400
        assert book.microprice == pytest.approx(expected)  # 0.55

    def test_empty_side_returns_none(self):
        book = OrderBook(token_id="t", ts=1.0, bids=[], asks=[Level(price=0.5, size=10)])
        assert book.best_bid is None
        assert book.mid is None
        assert book.microprice is None

    def test_levels_sorted_best_first(self):
        book = OrderBook(
            token_id="t", ts=1.0,
            bids=[Level(price=0.40, size=10), Level(price=0.45, size=10)],
            asks=[Level(price=0.60, size=10), Level(price=0.55, size=10)],
        )
        assert book.best_bid == 0.45
        assert book.best_ask == 0.55

    def test_depth_at_or_better(self):
        book = OrderBook(
            token_id="t", ts=1.0,
            bids=[Level(price=0.48, size=100), Level(price=0.45, size=50)],
            asks=[Level(price=0.52, size=80), Level(price=0.55, size=40)],
        )
        assert book.ask_depth_at_or_below(0.52) == 80
        assert book.ask_depth_at_or_below(0.55) == 120
        assert book.bid_depth_at_or_above(0.45) == 150


class TestOrderAndFill:
    def test_order_construction(self):
        o = Order(id="o1", intent=make_intent(), status=OrderStatus.CREATED,
                  created_ts=1.0, updated_ts=1.0)
        assert o.filled_size == 0.0
        assert o.remaining == 10.0

    def test_fill_fields(self):
        f = Fill(order_id="o1", token_id="t1", side=Side.BUY, price=0.5,
                 size=10, fee=0.05, ts=2.0, maker=False)
        assert f.notional == pytest.approx(5.0)


class TestPositionAndMarket:
    def test_position(self):
        p = Position(token_id="t1", size=100, avg_cost=0.40)
        assert p.mark_value(0.55) == pytest.approx(55.0)
        assert p.unrealized_pnl(0.55) == pytest.approx(15.0)

    def test_market_minimal(self):
        m = Market(condition_id="c1", question="Will X?", category="geopolitics",
                   token_id_yes="ty", token_id_no="tn", neg_risk=False,
                   end_date="2026-12-31T00:00:00Z", active=True)
        assert m.fee_schedule is None  # unknown until API provides
        assert m.fees_enabled is True  # conservative default: assume fees apply
        assert m.tick_size == 0.01
        assert m.min_size == 5.0
