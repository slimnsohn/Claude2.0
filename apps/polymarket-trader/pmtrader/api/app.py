"""Dashboard API: read-only state + token-guarded controls + WS push."""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"
ROOT_DIR = STATIC_DIR.parent


class ControlBody(BaseModel):
    token: str = ""


def build_app(orch, store, cfg) -> FastAPI:
    app = FastAPI(title="polymarket-trader", docs_url=None, redoc_url=None)

    def state_payload() -> dict:
        equity = orch.equity()
        marks = orch.marks()
        return {
            "mode": cfg.mode,
            "halted": orch.halted,
            "stop_reason": orch.stop_reason,
            "equity": round(equity, 2),
            "cash": round(orch.cash, 2),
            "bankroll_start": orch.bankroll.starting_equity,
            "bankroll_progress": round(orch.bankroll.progress(equity), 4),
            "double_or_bust": orch.bankroll.double_or_bust,
            "positions": [
                {"token_id": t, "size": round(p.size, 2),
                 "avg_cost": round(p.avg_cost, 4),
                 "mark": round(marks.get(t, p.avg_cost), 4),
                 "unrealized": round(p.unrealized_pnl(marks.get(t, p.avg_cost)), 2),
                 "condition_id": p.condition_id}
                for t, p in orch.positions.items()],
            "open_orders": [
                {"id": o.order_id, "token_id": o.intent.token_id,
                 "side": o.intent.side.value, "price": o.intent.price,
                 "size": o.intent.size, "filled": o.filled_size,
                 "strategy": o.intent.strategy, "status": o.status.value}
                for o in orch.backend.open_orders()] if hasattr(
                    orch.backend, "open_orders") else [],
            "n_markets": len(orch.markets),
            "ts": time.time(),
        }

    @app.get("/api/state")
    def state():
        return state_payload()

    @app.get("/api/strategies")
    def strategies():
        rows = []
        for s in orch.strategies:
            name = s.name
            live = orch.allocator.live_trades.get(name, [])
            paper = orch.allocator.paper_trades.get(name, [])
            rows.append({
                "name": name,
                "gate": str(orch.allocator.gate(name)),
                "backtest_pass": orch.allocator.backtest_pass.get(name),
                "weight": round(orch.allocator.weights().get(name, 0.0), 4),
                "budget": round(orch.allocator.budget(name), 2),
                "n_live_trades": len(live),
                "n_paper_trades": len(paper),
                "params": s.params,
            })
        return rows

    @app.get("/api/decisions")
    def decisions(limit: int = 100, strategy: str | None = None):
        return store.decisions(limit=min(limit, 500), strategy=strategy)

    @app.get("/api/equity")
    def equity_curve(since: float = 0.0):
        return store.equity_curve(since_ts=since)

    @app.get("/api/events")
    def allocator_events():
        return orch.allocator.events[-100:]

    @app.get("/api/walkforward")
    def walkforward():
        p = ROOT_DIR / "data" / "walkforward_report.json"
        if not p.exists():
            return JSONResponse(status_code=404, content={
                "error": "no report — run scripts/run_walkforward_gate.py"})
        return json.loads(p.read_text())

    @app.get("/api/execution")
    def execution():
        from pmtrader.backtest.execution_report import execution_report
        return execution_report(store)

    def check_token(body: ControlBody):
        if not cfg.dashboard.control_token or \
                body.token != cfg.dashboard.control_token:
            return JSONResponse(status_code=403,
                                content={"error": "bad control token"})
        return None

    @app.post("/api/control/kill")
    def kill(body: ControlBody):
        err = check_token(body)
        if err:
            return err
        orch.halt("dashboard kill switch", now=time.time())
        return {"ok": True, "halted": True}

    @app.post("/api/control/resume")
    def resume(body: ControlBody):
        err = check_token(body)
        if err:
            return err
        if orch.stop_reason and orch.stop_reason.startswith("bankroll"):
            # double-or-bust is a run-ending verdict, not a pause
            return JSONResponse(status_code=409, content={
                "error": f"cannot resume: {orch.stop_reason}"})
        orch.halted = False
        orch.stop_reason = None
        store.insert_decision(time.time(), "orchestrator", "resume",
                              {"via": "dashboard"})
        return {"ok": True, "halted": False}

    @app.websocket("/ws")
    async def ws(websocket: WebSocket):
        await websocket.accept()
        try:
            while True:
                await websocket.send_json(state_payload())
                await asyncio.sleep(2.0)
        except (WebSocketDisconnect, RuntimeError):
            return

    @app.get("/")
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    return app
