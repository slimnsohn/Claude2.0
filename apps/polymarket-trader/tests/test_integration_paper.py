"""End-to-end: recorded WSS tape -> book cache -> orchestrator -> strategies
-> risk -> paper fills -> dashboard API. Plus a planted arb so the full
pipeline provably produces fills, and a clean-shutdown check.
"""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pmtrader.api.app import build_app
from pmtrader.config import Config
from pmtrader.core.fees import FeeSchedule
from pmtrader.core.models import Level, Market, OrderBook, OrderStatus, Side
from pmtrader.datalayer.clob_ws import BookCache
from pmtrader.datalayer.store import Store
from pmtrader.execution.paper import PaperExecution
from pmtrader.orchestrator import Orchestrator
from pmtrader.strategies.s1_arb import S1Arb
from pmtrader.strategies.s2_mm import S2MarketMaker

FIXTURE = Path(__file__).parent / "fixtures" / "wss_market_sample.jsonl"
FREE = FeeSchedule(exponent=1, rate=0.0, taker_only=True, rebate_rate=0.0)


@pytest.fixture
def system(tmp_path):
    store = Store(tmp_path / "e2e.db")
    cfg = Config(mode="paper", bankroll=1000.0,
                 dashboard={"control_token": "t"})
    backend = PaperExecution(store=store, starting_cash=1000.0)
    orch = Orchestrator(cfg=cfg, store=store,
                        strategies=[S1Arb(), S2MarketMaker()],
                        backend=backend,
                        heartbeat_path=tmp_path / "hb")
    yield orch, store
    store.close()


def replay_tape_through(orch):
    """Feed the real recorded WSS tape via the production BookCache."""
    cache = BookCache()
    cache.on_book = orch.on_book
    cache.on_trade = orch.on_trade
    n = 0
    for line in FIXTURE.read_text(encoding="utf-8").splitlines():
        msgs = json.loads(line)
        if isinstance(msgs, dict):
            msgs = [msgs]
        for frame in msgs:
            cache.apply(frame)
            n += 1
    return n


class TestEndToEnd:
    def test_tape_replay_no_crashes_and_books_flow(self, system):
        orch, store = system
        n = replay_tape_through(orch)
        assert n > 100
        assert len(orch.books) >= 10  # books flowed into the orchestrator

    def test_planted_arb_full_pipeline(self, system):
        orch, store = system
        m = Market(condition_id="m1", question="Q?", category="geopolitics",
                   token_id_yes="m1-yes", token_id_no="m1-no", neg_risk=False,
                   end_date="2026-12-31T00:00:00Z", fee_schedule=FREE,
                   active=True)
        orch.register_market(m)
        replay_tape_through(orch)  # background noise from real tape
        # ts must be within the market's life (end 2026-12-31) and fresh
        now = 1_781_100_000.0  # 2026-06-10-ish, matches the tape era
        orch.on_book(OrderBook(token_id="m1-yes", ts=now,
                               bids=[Level(price=0.44, size=300)],
                               asks=[Level(price=0.46, size=300)]))
        orch.on_book(OrderBook(token_id="m1-no", ts=now,
                               bids=[Level(price=0.48, size=300)],
                               asks=[Level(price=0.50, size=300)]))
        fills = store.fills()
        assert {f["token_id"] for f in fills} == {"m1-yes", "m1-no"}
        sizes = {f["token_id"]: f["size"] for f in fills}
        assert sizes["m1-yes"] == sizes["m1-no"]  # legs equalized

        # equity reflects the position; decision log is complete
        assert orch.positions["m1-yes"].size > 0
        kinds = [d["kind"] for d in store.decisions(limit=20)]
        assert "approve" in kinds
        # dashboard reflects it all
        app = build_app(orch, store, orch.cfg)
        with TestClient(app) as client:
            state = client.get("/api/state").json()
            assert len(state["positions"]) == 2
            assert state["equity"] == pytest.approx(orch.equity(), abs=0.01)

    def test_clean_shutdown_cancels_resting_orders(self, system):
        orch, store = system
        m = Market(condition_id="m2", question="Q?", category="geopolitics",
                   token_id_yes="m2-yes", token_id_no="m2-no", neg_risk=False,
                   end_date="2026-12-31T00:00:00Z", fee_schedule=FREE,
                   active=True)
        orch.register_market(m)
        # a resting (non-marketable) order via direct backend submit
        from pmtrader.core.models import Intent
        rec = orch.backend.submit(Intent(
            strategy="s1_arb", token_id="m2-yes", side=Side.BUY, price=0.30,
            size=10, expected_edge=0.05, reasoning="resting test",
            condition_id="m2"), now=100.0)
        assert rec.status == OrderStatus.OPEN
        orch.shutdown(now=101.0)
        assert orch.backend.open_orders() == []
        assert rec.status == OrderStatus.CANCELLED
