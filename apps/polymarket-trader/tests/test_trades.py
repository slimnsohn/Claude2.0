"""closed_trades(): FIFO reconstruction of per-strategy P&L from the store."""
import pytest

from pmtrader.core.models import Fill, Intent, Market, Order, OrderStatus, Side
from pmtrader.datalayer.store import Store
from pmtrader.datalayer.trades import closed_trades


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "t.db")
    yield s
    s.close()


def put_order(store, order_id, strategy, token, side=Side.BUY, price=0.5):
    intent = Intent(strategy=strategy, token_id=token, side=side, price=price,
                    size=10.0, expected_edge=0.01, reasoning="t")
    store.upsert_order(Order(id=order_id, intent=intent,
                             status=OrderStatus.FILLED,
                             created_ts=1.0, updated_ts=2.0))


def put_fill(store, order_id, token, side, price, size, ts, fee=0.0):
    store.insert_fill(Fill(order_id=order_id, token_id=token, side=side,
                           price=price, size=size, fee=fee, ts=ts))


def put_market(store, cid="m1"):
    store.upsert_market(Market(condition_id=cid, question="Q?",
                               token_id_yes=f"{cid}-yes",
                               token_id_no=f"{cid}-no"))


class TestClosedTrades:
    def test_buy_then_sell_realizes_pnl_with_fees(self, store):
        put_order(store, "paper-a-1", "s1_arb", "tokA")
        put_fill(store, "paper-a-1", "tokA", Side.BUY, 0.40, 10.0, ts=100.0, fee=0.10)
        put_order(store, "paper-a-2", "s1_arb", "tokA", side=Side.SELL)
        put_fill(store, "paper-a-2", "tokA", Side.SELL, 0.60, 10.0, ts=200.0, fee=0.10)
        out = closed_trades(store)
        trades = out["paper"]["s1_arb"]
        assert len(trades) == 1
        # cost 4.0+0.10, proceeds 6.0-0.10 -> pnl 1.8
        assert trades[0]["pnl"] == pytest.approx(1.8)
        assert trades[0]["ts"] == 200.0

    def test_resolution_settles_open_lot(self, store):
        put_market(store, "m1")
        put_order(store, "paper-a-1", "s4_calib", "m1-yes")
        put_fill(store, "paper-a-1", "m1-yes", Side.BUY, 0.55, 20.0, ts=100.0)
        store.set_resolution("m1", winning_token_id="m1-yes", resolved_ts=900.0)
        out = closed_trades(store)
        trades = out["paper"]["s4_calib"]
        assert len(trades) == 1
        assert trades[0]["pnl"] == pytest.approx(20.0 - 11.0)  # payout - cost
        assert trades[0]["ts"] == 900.0

    def test_losing_resolution_pays_zero(self, store):
        put_market(store, "m1")
        put_order(store, "paper-a-1", "s4_calib", "m1-yes")
        put_fill(store, "paper-a-1", "m1-yes", Side.BUY, 0.55, 20.0, ts=100.0)
        store.set_resolution("m1", winning_token_id="m1-no", resolved_ts=900.0)
        out = closed_trades(store)
        assert out["paper"]["s4_calib"][0]["pnl"] == pytest.approx(-11.0)

    def test_unresolved_open_lot_is_not_a_trade(self, store):
        put_market(store, "m1")
        put_order(store, "paper-a-1", "s4_calib", "m1-yes")
        put_fill(store, "paper-a-1", "m1-yes", Side.BUY, 0.55, 20.0, ts=100.0)
        out = closed_trades(store)
        assert out["paper"] == {}

    def test_partial_sell_fifo(self, store):
        put_order(store, "paper-a-1", "s1_arb", "tokA")
        put_fill(store, "paper-a-1", "tokA", Side.BUY, 0.40, 10.0, ts=100.0)
        put_fill(store, "paper-a-1", "tokA", Side.BUY, 0.50, 10.0, ts=110.0)
        put_order(store, "paper-a-2", "s1_arb", "tokA", side=Side.SELL)
        put_fill(store, "paper-a-2", "tokA", Side.SELL, 0.60, 15.0, ts=200.0)
        out = closed_trades(store)
        trades = out["paper"]["s1_arb"]
        # first lot (10 @ .40) fully closed, second lot 5 of 10 @ .50 closed
        assert len(trades) == 2
        assert sum(t["pnl"] for t in trades) == pytest.approx(
            (0.60 - 0.40) * 10 + (0.60 - 0.50) * 5)

    def test_live_and_paper_split_by_order_id_prefix(self, store):
        put_order(store, "paper-a-1", "s1_arb", "tokA")
        put_fill(store, "paper-a-1", "tokA", Side.BUY, 0.4, 5.0, ts=1.0)
        put_order(store, "0xlive1", "s1_arb", "tokB")
        put_fill(store, "0xlive1", "tokB", Side.BUY, 0.4, 5.0, ts=1.0)
        put_order(store, "paper-a-2", "s1_arb", "tokA", side=Side.SELL)
        put_fill(store, "paper-a-2", "tokA", Side.SELL, 0.5, 5.0, ts=2.0)
        put_order(store, "0xlive2", "s1_arb", "tokB", side=Side.SELL)
        put_fill(store, "0xlive2", "tokB", Side.SELL, 0.5, 5.0, ts=2.0)
        out = closed_trades(store)
        assert len(out["paper"]["s1_arb"]) == 1
        assert len(out["live"]["s1_arb"]) == 1

    def test_orphan_fill_without_order_is_skipped(self, store):
        put_fill(store, "ghost-1", "tokA", Side.BUY, 0.4, 5.0, ts=1.0)
        assert closed_trades(store) == {"paper": {}, "live": {}}
