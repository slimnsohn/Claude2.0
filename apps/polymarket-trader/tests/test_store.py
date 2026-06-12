import gzip
import json

import pytest

from pmtrader.core.fees import FeeSchedule
from pmtrader.core.models import Fill, Intent, Market, Side
from pmtrader.datalayer.archive import Archive
from pmtrader.datalayer.store import Store


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "test.db")
    yield s
    s.close()


def make_market(**overrides):
    base = dict(
        condition_id="c1", question="Will X happen?", category="geopolitics",
        token_id_yes="ty1", token_id_no="tn1", neg_risk=False,
        end_date="2026-12-31T00:00:00Z", active=True,
        fee_schedule=FeeSchedule(exponent=1, rate=0.0, taker_only=True, rebate_rate=0.25),
    )
    base.update(overrides)
    return Market(**base)


class TestStore:
    def test_wal_mode_enabled(self, store):
        assert store.journal_mode().lower() == "wal"

    def test_market_roundtrip(self, store):
        m = make_market()
        store.upsert_market(m)
        got = store.get_market("c1")
        assert got == m

    def test_market_upsert_overwrites(self, store):
        store.upsert_market(make_market())
        store.upsert_market(make_market(active=False))
        assert store.get_market("c1").active is False
        assert len(store.all_markets()) == 1

    def test_intent_roundtrip_preserves_reasoning(self, store):
        i = Intent(strategy="s1", token_id="ty1", side=Side.BUY, price=0.46,
                   size=100, expected_edge=0.03, reasoning="sum=0.9600 arb")
        intent_id = store.insert_intent(i, ts=123.0)
        rows = store.intents(limit=10)
        assert rows[0]["reasoning"] == "sum=0.9600 arb"
        assert rows[0]["id"] == intent_id
        assert rows[0]["strategy"] == "s1"

    def test_fill_roundtrip(self, store):
        f = Fill(order_id="o1", token_id="ty1", side=Side.BUY, price=0.46,
                 size=100, fee=0.0, ts=124.0, maker=False)
        store.insert_fill(f)
        fills = store.fills(token_id="ty1")
        assert len(fills) == 1 and fills[0]["price"] == pytest.approx(0.46)

    def test_price_history_bulk_and_query(self, store):
        points = [(1000.0 + i * 60, 0.40 + i * 0.001) for i in range(100)]
        store.insert_price_history("ty1", points)
        got = store.price_history("ty1", start_ts=1000.0 + 60 * 50)
        assert len(got) == 50
        assert got[0] == (1000.0 + 60 * 50, pytest.approx(0.45))

    def test_price_history_idempotent(self, store):
        store.insert_price_history("ty1", [(1000.0, 0.5)])
        store.insert_price_history("ty1", [(1000.0, 0.5)])
        assert len(store.price_history("ty1")) == 1

    def test_equity_curve_ordered(self, store):
        store.insert_equity_snapshot(ts=200.0, equity=1010.0, cash=500.0, mode="paper")
        store.insert_equity_snapshot(ts=100.0, equity=1000.0, cash=1000.0, mode="paper")
        curve = store.equity_curve()
        assert [p["ts"] for p in curve] == [100.0, 200.0]

    def test_decision_log(self, store):
        store.insert_decision(ts=1.0, strategy="risk", kind="veto",
                              payload={"rule": "max_market_frac", "detail": "5.2% > 5%"})
        rows = store.decisions(limit=5)
        assert rows[0]["kind"] == "veto"
        assert rows[0]["payload"]["rule"] == "max_market_frac"

    def test_resolution_roundtrip(self, store):
        store.upsert_market(make_market())
        store.set_resolution("c1", winning_token_id="ty1", resolved_ts=999.0)
        res = store.resolutions()
        assert res == [{"condition_id": "c1", "winning_token_id": "ty1", "resolved_ts": 999.0}]


class TestNewHelpers:
    def test_all_orders_roundtrip(self, store):
        from pmtrader.core.models import Intent, Order, OrderStatus, Side
        intent = Intent(strategy="s1_arb", token_id="tokA", side=Side.BUY,
                        price=0.5, size=10.0, expected_edge=0.01, reasoning="t")
        store.upsert_order(Order(id="paper-x-1", intent=intent,
                                 status=OrderStatus.FILLED,
                                 created_ts=1.0, updated_ts=2.0))
        orders = store.all_orders()
        assert len(orders) == 1 and orders[0].id == "paper-x-1"
        assert orders[0].intent.strategy == "s1_arb"

    def test_last_decision_ts(self, store):
        assert store.last_decision_ts("demotion", "s1_arb") is None
        store.insert_decision(100.0, "s1_arb", "demotion", {})
        store.insert_decision(200.0, "s1_arb", "demotion", {})
        store.insert_decision(300.0, "s2_mm", "demotion", {})
        assert store.last_decision_ts("demotion", "s1_arb") == 200.0

    def test_price_history_span(self, store):
        assert store.price_history_span() == (None, None)
        store.insert_price_history("tokA", [(10.0, 0.5), (30.0, 0.6)])
        store.insert_price_history("tokB", [(20.0, 0.4)])
        assert store.price_history_span() == (10.0, 30.0)


class TestArchive:
    def test_write_and_read_back(self, tmp_path):
        a = Archive(tmp_path / "arch")
        p = a.write("gamma", {"hello": [1, 2, 3]}, tag="markets", ts=1700000000.0)
        assert p.exists() and p.suffix == ".gz"
        assert json.loads(gzip.decompress(p.read_bytes())) == {"hello": [1, 2, 3]}

    def test_listing(self, tmp_path):
        a = Archive(tmp_path / "arch")
        a.write("gamma", {"a": 1}, tag="x", ts=1700000000.0)
        a.write("clob", {"b": 2}, tag="y", ts=1700000001.0)
        assert len(a.list("gamma")) == 1
        assert len(a.list("clob")) == 1
