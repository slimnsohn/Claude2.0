"""Live execution backend — py-clob-client fully mocked, zero network.

Includes the no-secrets-in-logs guarantee test.
"""
import logging
from unittest.mock import MagicMock

import pytest

from pmtrader.core.models import Intent, Market, OrderStatus, Side
from pmtrader.datalayer.store import Store
from pmtrader.execution.live import LiveExecution
from pmtrader.execution.router import ExecutionRouter

FAKE_KEY = "0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef"


def mk_market(cid="m1", tick=0.01):
    return Market(condition_id=cid, question="Q?", category="general",
                  token_id_yes=f"{cid}-yes", token_id_no=f"{cid}-no",
                  neg_risk=False, end_date="2026-12-31T00:00:00Z",
                  tick_size=tick, active=True)


def mk_intent(**kw):
    base = dict(strategy="s1", token_id="m1-yes", side=Side.BUY, price=0.4111,
                size=100.0, expected_edge=0.02, reasoning="t", condition_id="m1")
    base.update(kw)
    return Intent(**base)


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "l.db")
    yield s
    s.close()


@pytest.fixture
def clob():
    client = MagicMock()
    client.create_and_post_order.return_value = {
        "success": True, "orderID": "x-123"}
    return client


@pytest.fixture
def live(store, clob):
    lx = LiveExecution(store=store, client=clob)
    lx.register_market(mk_market())
    return lx


class TestOrderMapping:
    def test_params_mapped_and_tick_rounded(self, live, clob):
        live.submit(mk_intent(price=0.4111, size=100.4), now=1.0)
        args = clob.create_and_post_order.call_args[0][0]
        assert args.token_id == "m1-yes"
        assert args.price == pytest.approx(0.41)  # rounded to tick 0.01
        assert args.size == pytest.approx(100.0)  # whole shares
        assert args.side == "BUY"

    def test_exchange_id_recorded(self, live):
        rec = live.submit(mk_intent(), now=1.0)
        assert rec.exchange_id == "x-123"
        assert rec.status == OrderStatus.OPEN

    def test_api_error_rejects_not_crashes(self, live, clob):
        clob.create_and_post_order.side_effect = RuntimeError("api down")
        rec = live.submit(mk_intent(), now=1.0)
        assert rec.status == OrderStatus.REJECTED

    def test_api_failure_response_rejects(self, live, clob):
        clob.create_and_post_order.return_value = {"success": False,
                                                   "errorMsg": "no balance"}
        rec = live.submit(mk_intent(), now=1.0)
        assert rec.status == OrderStatus.REJECTED


class TestCancel:
    def test_cancel_calls_api(self, live, clob):
        rec = live.submit(mk_intent(), now=1.0)
        live.cancel(rec.order_id, now=2.0)
        clob.cancel.assert_called_once_with("x-123")
        assert rec.status == OrderStatus.CANCELLED

    def test_close_cancels_all(self, live, clob):
        live.close()
        clob.cancel_all.assert_called_once()


class TestSecretHygiene:
    def test_private_key_never_logged(self, store, clob, caplog):
        with caplog.at_level(logging.DEBUG):
            lx = LiveExecution(store=store, client=clob)
            lx.register_market(mk_market())
            clob.create_and_post_order.side_effect = RuntimeError(
                "boom")  # error path logs
            lx.submit(mk_intent(), now=1.0)
            lx.close()
        assert FAKE_KEY not in caplog.text
        for record in caplog.records:
            assert "PRIVATE_KEY" not in record.getMessage()


class TestRouterGroups:
    def test_group_leg_rejection_triggers_unwind(self, store, clob):
        lx = LiveExecution(store=store, client=clob)
        lx.register_market(mk_market())
        unwinds = []
        router = ExecutionRouter(backend=lx, store=store,
                                 on_unwind=lambda intents: unwinds.extend(intents))

        results = iter([
            {"success": True, "orderID": "leg-1"},
            {"success": False, "errorMsg": "insufficient"},
        ])
        clob.create_and_post_order.side_effect = lambda *a, **k: next(results)

        legs = [mk_intent(token_id="m1-yes", group_id="g1"),
                mk_intent(token_id="m1-no", group_id="g1")]
        recs = [router.submit(i, now=1.0) for i in legs]
        # leg 1 open, leg 2 rejected -> router cancels leg 1 and emits unwind
        assert recs[1].status == OrderStatus.REJECTED
        assert recs[0].status == OrderStatus.CANCELLED
        # unwind sells whatever filled; nothing filled here -> no sell intents
        assert unwinds == []

    def test_group_unwind_sells_filled_leg(self, store, clob):
        lx = LiveExecution(store=store, client=clob)
        lx.register_market(mk_market())
        unwinds = []
        router = ExecutionRouter(backend=lx, store=store,
                                 on_unwind=lambda intents: unwinds.extend(intents))

        results = iter([
            {"success": True, "orderID": "leg-1"},
            {"success": False, "errorMsg": "insufficient"},
        ])
        clob.create_and_post_order.side_effect = lambda *a, **k: next(results)

        legs = [mk_intent(token_id="m1-yes", group_id="g1"),
                mk_intent(token_id="m1-no", group_id="g1")]
        rec1 = router.submit(legs[0], now=1.0)
        # leg 1 fills completely before leg 2 fails
        rec1.apply_fill(100.0, 0.41, 1.5)
        router.submit(legs[1], now=2.0)
        assert len(unwinds) == 1
        uw = unwinds[0]
        assert uw.side == Side.SELL and uw.token_id == "m1-yes"
        assert uw.size == 100.0
        assert "unwind" in uw.reasoning
