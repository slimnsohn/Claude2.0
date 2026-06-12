"""Entry point: python -m pmtrader

Builds everything from config/settings.yaml and runs the orchestrator with
the dashboard mounted in-process. Paper mode unless the live interlock is
fully armed (see config.py).
"""
from __future__ import annotations

import asyncio
import json
import logging
import signal
import sys
from pathlib import Path

import uvicorn

from pmtrader.api.app import build_app
from pmtrader.config import load_config
from pmtrader.core.lock import TRADER_LOCK_PORT, acquire_single_instance_lock
from pmtrader.datalayer.clob_rest import ClobRestClient
from pmtrader.datalayer.clob_ws import ClobMarketFeed
from pmtrader.datalayer.coinbase import CoinbaseClient
from pmtrader.datalayer.gamma import GammaClient
from pmtrader.datalayer.store import Store
from pmtrader.execution.paper import PaperExecution
from pmtrader.orchestrator import Orchestrator
from pmtrader.strategies.s1_arb import S1Arb
from pmtrader.strategies.s2_mm import S2MarketMaker
from pmtrader.strategies.s3_crypto import S3Crypto
from pmtrader.strategies.s4_calib import S4Calib

ROOT = Path(__file__).resolve().parent.parent

log = logging.getLogger("pmtrader")


def build_strategies(cfg) -> list:
    out = []
    sconf = cfg.strategies

    def params_for(name):
        p = dict(sconf.get(name, {}))
        p.pop("enabled", None)
        return p or None

    if sconf.get("s1_arb", {}).get("enabled", True):
        out.append(S1Arb(params=params_for("s1_arb")))
    if sconf.get("s2_mm", {}).get("enabled", True):
        out.append(S2MarketMaker(params=params_for("s2_mm")))
    if sconf.get("s3_crypto", {}).get("enabled", True):
        out.append(S3Crypto(params=params_for("s3_crypto")))
    if sconf.get("s4_calib", {}).get("enabled", True):
        wl_path = ROOT / "config" / "strategies" / "s4_whitelist.json"
        whitelist = json.loads(wl_path.read_text()) if wl_path.exists() else []
        out.append(S4Calib(params=params_for("s4_calib"), whitelist=whitelist))
    return out


async def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    # two traders sharing one DB/heartbeat/port corrupt the run — refuse.
    # exit 0 so a duplicate watchdog treats it as a clean exit and stops.
    instance_lock = acquire_single_instance_lock(TRADER_LOCK_PORT)
    if instance_lock is None:
        log.error("another pmtrader instance is already running — exiting")
        return 0
    cfg = load_config(ROOT / "config" / "settings.yaml")

    store = Store(ROOT / "data" / "pmtrader.db")
    gamma = GammaClient()
    clob = ClobRestClient()
    coinbase = CoinbaseClient()
    feed = ClobMarketFeed(assets=[])

    if cfg.mode == "live":
        from pmtrader.execution.live import LiveExecution, make_clob_client
        backend = LiveExecution(store=store, client=make_clob_client())
        log.warning("LIVE MODE — real orders will be signed.")
    else:
        backend = PaperExecution(store=store, starting_cash=cfg.bankroll)
        log.info("paper mode — fills are simulated against the live book")

    orch = Orchestrator(cfg=cfg, store=store, strategies=build_strategies(cfg),
                        backend=backend, heartbeat_path=ROOT / "data" / "heartbeat",
                        gamma=gamma, coinbase=coinbase, feed=feed)

    wf_path = ROOT / "data" / "walkforward_report.json"
    if wf_path.exists():
        wf = json.loads(wf_path.read_text())
        orch.allocator.set_backtest_pass(
            {name: bool(r.get("pass"))
             for name, r in wf.get("strategies", {}).items()})
        log.info("walk-forward gate loaded: %s",
                 {n: r.get("pass") for n, r in wf.get("strategies", {}).items()})

    app = build_app(orch, store, cfg)
    server = uvicorn.Server(uvicorn.Config(
        app, host=cfg.dashboard.host, port=cfg.dashboard.port,
        log_level="warning"))

    loop = asyncio.get_running_loop()
    stop_evt = asyncio.Event()
    for sig in ("SIGINT", "SIGTERM"):
        if hasattr(signal, sig):
            try:
                loop.add_signal_handler(getattr(signal, sig), stop_evt.set)
            except NotImplementedError:  # Windows
                pass

    tasks = [asyncio.create_task(orch.run()),
             asyncio.create_task(server.serve()),
             asyncio.create_task(stop_evt.wait())]
    try:
        done, pending = await asyncio.wait(tasks,
                                           return_when=asyncio.FIRST_COMPLETED)
    finally:
        orch.shutdown()
        feed.stop()
        for t in tasks:
            t.cancel()
        await gamma.close()
        await clob.close()
        await coinbase.close()
        store.close()
    log.info("pmtrader exited (%s)", orch.stop_reason or "signal")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        sys.exit(0)
