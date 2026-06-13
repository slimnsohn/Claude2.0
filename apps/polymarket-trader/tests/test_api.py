"""Dashboard API tests via FastAPI TestClient (no network)."""
import pytest
from fastapi.testclient import TestClient

from pmtrader.api.app import build_app
from pmtrader.config import Config
from pmtrader.core.fees import FeeSchedule
from pmtrader.core.models import Level, Market, OrderBook
from pmtrader.datalayer.store import Store
from pmtrader.execution.paper import PaperExecution
from pmtrader.orchestrator import Orchestrator
from pmtrader.strategies.s1_arb import S1Arb

FREE = FeeSchedule(exponent=1, rate=0.0, taker_only=True, rebate_rate=0.0)
TOKEN = "test-token-123"


@pytest.fixture
def client(tmp_path):
    store = Store(tmp_path / "api.db")
    cfg = Config(mode="paper", bankroll=1000.0,
                 dashboard={"control_token": TOKEN})
    backend = PaperExecution(store=store, starting_cash=1000.0)
    orch = Orchestrator(cfg=cfg, store=store, strategies=[S1Arb()],
                        backend=backend)
    m = Market(condition_id="m1", question="Q?", category="geopolitics",
               token_id_yes="m1-yes", token_id_no="m1-no", neg_risk=False,
               end_date="2026-12-31T00:00:00Z", fee_schedule=FREE, active=True)
    orch.register_market(m)
    orch.on_book(OrderBook(token_id="m1-yes", ts=100.0,
                           bids=[Level(price=0.44, size=300)],
                           asks=[Level(price=0.46, size=300)]))
    orch.on_book(OrderBook(token_id="m1-no", ts=100.0,
                           bids=[Level(price=0.48, size=300)],
                           asks=[Level(price=0.50, size=300)]))
    app = build_app(orch, store, cfg)
    with TestClient(app) as c:
        c.orch = orch
        c.store = store
        yield c
    store.close()


class TestState:
    def test_state_shape(self, client):
        r = client.get("/api/state")
        assert r.status_code == 200
        body = r.json()
        assert body["mode"] == "paper"
        assert body["halted"] is False
        assert "equity" in body and "cash" in body
        assert "bankroll_progress" in body
        assert isinstance(body["positions"], list)
        assert isinstance(body["open_orders"], list)

    def test_positions_present_after_arb(self, client):
        body = client.get("/api/state").json()
        tokens = {p["token_id"] for p in body["positions"]}
        assert tokens == {"m1-yes", "m1-no"}  # planted arb filled both legs


class TestStrategies:
    def test_strategy_panel(self, client):
        r = client.get("/api/strategies")
        assert r.status_code == 200
        rows = r.json()
        s1 = next(s for s in rows if s["name"] == "s1_arb")
        assert s1["gate"] == "PAPER"
        assert "weight" in s1 and "budget" in s1


class TestDecisions:
    def test_decision_log_newest_first(self, client):
        r = client.get("/api/decisions?limit=50")
        assert r.status_code == 200
        rows = r.json()
        assert rows  # approvals from the planted arb
        ids = [row["id"] for row in rows]
        assert ids == sorted(ids, reverse=True)


class TestControls:
    def test_kill_requires_token(self, client):
        r = client.post("/api/control/kill", json={})
        assert r.status_code == 403
        r = client.post("/api/control/kill", json={"token": "wrong"})
        assert r.status_code == 403
        assert client.orch.halted is False

    def test_kill_with_token_halts(self, client):
        r = client.post("/api/control/kill", json={"token": TOKEN})
        assert r.status_code == 200
        assert client.orch.halted is True

    def test_resume_with_token(self, client):
        client.post("/api/control/kill", json={"token": TOKEN})
        r = client.post("/api/control/resume", json={"token": TOKEN})
        assert r.status_code == 200
        assert client.orch.halted is False

    def test_resume_refused_after_bankroll_verdict(self, client):
        # double-or-bust is a run-ending verdict; the dashboard cannot undo it
        client.orch.halt("bankroll verdict: RunVerdict.STOP_LOST", now=100.0)
        r = client.post("/api/control/resume", json={"token": TOKEN})
        assert r.status_code == 409
        assert client.orch.halted is True


class TestWebSocket:
    def test_ws_pushes_state(self, client):
        with client.websocket_connect("/ws") as ws:
            msg = ws.receive_json()
            assert msg["mode"] == "paper"
            assert "equity" in msg


class TestStatic:
    def test_index_served(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert "polymarket" in r.text.lower()


class TestBacktestSurfaces:
    def test_strategies_include_backtest_pass(self, client):
        client.orch.allocator.set_backtest_pass({"s1_arb": True})
        rows = client.get("/api/strategies").json()
        row = next(r for r in rows if r["name"] == "s1_arb")
        assert row["backtest_pass"] is True

    def test_strategies_backtest_pass_none_when_unknown(self, client):
        rows = client.get("/api/strategies").json()
        row = next(r for r in rows if r["name"] == "s1_arb")
        assert row["backtest_pass"] is None

    def test_walkforward_endpoint_exists(self, client):
        # 200 if a real report exists on disk, 404 with a hint otherwise
        r = client.get("/api/walkforward")
        assert r.status_code in (200, 404)
        if r.status_code == 404:
            assert "run_walkforward_gate" in r.json()["error"]

    def test_execution_report_endpoint(self, client):
        rep = client.get("/api/execution").json()
        assert "makers" in rep and "takers" in rep
