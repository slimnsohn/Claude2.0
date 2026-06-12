"""Execution realism report: what paper trading is FOR under backtest-first."""
import pytest

from pmtrader.backtest.execution_report import execution_report
from pmtrader.core.models import Fill, Intent, Order, OrderStatus, Side
from pmtrader.datalayer.store import Store


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "e.db")
    yield s
    s.close()


def put(store, order_id, status, post_only=False, created_ts=100.0,
        fills=()):
    intent = Intent(strategy="s2_mm", token_id="tokA", side=Side.BUY,
                    price=0.50, size=10.0, expected_edge=0.01, reasoning="t",
                    post_only=post_only)
    store.upsert_order(Order(id=order_id, intent=intent, status=status,
                             created_ts=created_ts, updated_ts=created_ts))
    for price, size, ts, maker in fills:
        store.insert_fill(Fill(order_id=order_id, token_id="tokA",
                               side=Side.BUY, price=price, size=size,
                               fee=0.0, ts=ts, maker=maker))


class TestExecutionReport:
    def test_maker_fill_rate_and_time_to_fill(self, store):
        put(store, "paper-r-1", OrderStatus.FILLED, post_only=True,
            created_ts=100.0, fills=[(0.50, 10.0, 160.0, True)])
        put(store, "paper-r-2", OrderStatus.CANCELLED, post_only=True)
        rep = execution_report(store)
        assert rep["makers"]["n_resting_orders"] == 2
        assert rep["makers"]["n_filled"] == 1
        assert rep["makers"]["fill_rate"] == pytest.approx(0.5)
        assert rep["makers"]["median_secs_to_fill"] == pytest.approx(60.0)

    def test_taker_stats(self, store):
        put(store, "paper-r-3", OrderStatus.FILLED,
            fills=[(0.48, 10.0, 100.0, False)])
        rep = execution_report(store)
        assert rep["takers"]["n_orders"] == 1
        # BUY filled 2 cents under the limit -> improvement +0.02/share
        assert rep["takers"]["avg_improvement_per_share"] == pytest.approx(0.02)

    def test_live_orders_excluded(self, store):
        put(store, "0xlive-1", OrderStatus.FILLED,
            fills=[(0.48, 10.0, 100.0, False)])
        rep = execution_report(store)
        assert rep["n_paper_orders"] == 0
