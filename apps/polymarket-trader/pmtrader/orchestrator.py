"""Orchestrator: the autonomous trading loop.

Wires feeds -> strategies -> allocator -> risk -> execution, owns the
canonical cash/position ledger (fed by fill events from whichever backend is
active), takes equity snapshots, enforces the bankroll verdict, and touches
the heartbeat file the watchdog monitors. One instance per process.
"""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Optional

from pmtrader.allocator import Allocator, GateStatus
from pmtrader.config import Config
from pmtrader.core.bankroll import Bankroll, RunVerdict
from pmtrader.core.models import (
    Fill, Intent, Market, OrderBook, OrderStatus, Position, Side,
)
from pmtrader.execution.paper import PaperExecution
from pmtrader.execution.router import ExecutionRouter
from pmtrader.risk import Approved, PortfolioSnapshot, RiskManager, Veto
from pmtrader.strategies.base import Strategy, StrategyContext
from pmtrader.strategies.s3_crypto import ewma_vol_annualized

log = logging.getLogger(__name__)


class Orchestrator:
    def __init__(self, cfg: Config, store, strategies: list[Strategy],
                 backend, heartbeat_path: Optional[Path] = None,
                 gamma=None, coinbase=None, feed=None):
        self.cfg = cfg
        self.store = store
        self.strategies = strategies
        self.backend = backend
        self.gamma = gamma
        self.coinbase = coinbase
        self.feed = feed
        self.heartbeat_path = heartbeat_path

        self.risk = RiskManager(rules={**self.risk_defaults(), **cfg.risk})
        self.bankroll = Bankroll(starting_equity=cfg.bankroll,
                                 double_or_bust=cfg.double_or_bust)
        self.allocator = Allocator([s.name for s in strategies], cfg.bankroll)
        self.router = ExecutionRouter(backend=backend, store=store,
                                      on_unwind=self._submit_unwinds)

        self.cash = cfg.bankroll
        self.positions: dict[str, Position] = {}
        self.books: dict[str, OrderBook] = {}
        self.markets: dict[str, Market] = {}
        self._token_market: dict[str, Market] = {}
        self.halted = False
        self.stop_reason: Optional[str] = None
        self._shutdown_done = False
        self._strategy_errors: dict[str, int] = {}

        backend.on_fill_callbacks.append(self._on_fill)

    @staticmethod
    def risk_defaults() -> dict:
        from pmtrader.risk import DEFAULT_RULES
        return dict(DEFAULT_RULES)

    # -- ledger ----------------------------------------------------------------
    def _on_fill(self, fill: Fill, order) -> None:
        cost = fill.price * fill.size
        if fill.side == Side.BUY:
            self.cash -= cost + fill.fee
            pos = self.positions.get(fill.token_id)
            if pos is None:
                pos = Position(token_id=fill.token_id, size=0.0, avg_cost=0.0,
                               condition_id=order.intent.condition_id,
                               event_id=order.intent.event_id)
                self.positions[fill.token_id] = pos
            total = pos.avg_cost * pos.size + cost + fill.fee
            pos.size += fill.size
            pos.avg_cost = total / pos.size
        else:
            self.cash += cost - fill.fee
            pos = self.positions.get(fill.token_id)
            if pos is not None:
                pos.size -= fill.size
                if pos.size <= 1e-9:
                    self.positions.pop(fill.token_id, None)
        for s in self.strategies:
            if s.name == order.intent.strategy:
                s.on_fill(fill)

    def marks(self) -> dict[str, float]:
        out = {}
        for token_id, pos in self.positions.items():
            book = self.books.get(token_id)
            out[token_id] = book.mid if book and book.mid else pos.avg_cost
        return out

    def equity(self) -> float:
        marks = self.marks()
        return self.cash + sum(p.size * marks.get(t, p.avg_cost)
                               for t, p in self.positions.items())

    # -- snapshot for risk -------------------------------------------------------
    def snapshot(self, now: float) -> PortfolioSnapshot:
        eq = self.equity()
        self.bankroll.mark_day(now, eq)
        return PortfolioSnapshot(
            now=now, cash=self.cash, equity=eq,
            day_pnl=self.bankroll.day_pnl(eq),
            positions=dict(self.positions), marks=self.marks(),
            books=self.books, markets=self.markets, halted=self.halted)

    # -- intent pipeline -----------------------------------------------------------
    def process_intents(self, intents: list[Intent], now: float) -> None:
        singles, groups = [], {}
        for intent in intents:
            if intent.group_id:
                groups.setdefault(intent.group_id, []).append(intent)
            else:
                singles.append(intent)
        for intent in singles:
            decision = self._check_one(intent, now)
            if decision is not None:
                self.router.submit(decision, now)
        # groups are all-or-nothing: every leg must pass risk, and legs are
        # equalized to the smallest approved size so the structure stays hedged
        for group_id, legs in groups.items():
            checked = [self._check_one(leg, now) for leg in legs]
            if any(c is None for c in checked):
                self.store.insert_decision(now, "risk", "group_reject", {
                    "group_id": group_id,
                    "detail": "one or more legs vetoed; group dropped"})
                continue
            min_size = min(c.size for c in checked)
            for leg in checked:
                sized = leg if leg.size == min_size else \
                    leg.model_copy(update={"size": min_size})
                self.router.submit(sized, now)

    def _check_one(self, intent: Intent, now: float) -> Optional[Intent]:
        """Persist, gate-check, risk-check. Returns the (possibly downsized)
        intent if approved, else None."""
        intent_id = self.store.insert_intent(intent, ts=now)
        gate = self.allocator.gate(intent.strategy) \
            if intent.strategy in self.allocator.strategies else None
        if (self.cfg.mode == "live" and gate is not None
                and gate != GateStatus.LIVE_ELIGIBLE
                and intent.side == Side.BUY):
            self.store.insert_decision(now, intent.strategy, "gate_block", {
                "intent_id": intent_id, "gate": str(gate)})
            return None
        decision = self.risk.check(intent, self.snapshot(now))
        if isinstance(decision, Veto):
            self.store.insert_decision(now, "risk", "veto", {
                "intent_id": intent_id, "rule": decision.rule,
                "detail": decision.detail, "strategy": intent.strategy})
            return None
        self.store.insert_decision(now, "risk", "approve", {
            "intent_id": intent_id, "detail": decision.detail,
            "strategy": intent.strategy})
        return intent if decision.size == intent.size else \
            intent.model_copy(update={"size": decision.size})

    def _submit_unwinds(self, intents: list[Intent]) -> None:
        if intents:
            self.process_intents(intents, now=time.time())

    # -- market data entry points ------------------------------------------------------
    def on_book(self, book: OrderBook) -> None:
        self.books[book.token_id] = book
        if hasattr(self.backend, "on_book"):
            self.backend.on_book(book)
        market = self._token_market.get(book.token_id)
        if market is None or self.halted:
            return
        now = book.ts
        positions = dict(self.positions)
        for s in self.strategies:
            ctx = StrategyContext(now=now, cash=self.cash,
                                  budget=self.allocator.budget(s.name),
                                  positions=positions)
            # one buggy strategy must not take down the tick loop (the feed
            # would silently stall while the heartbeat keeps beating)
            try:
                intents = s.on_books(market, self.books, ctx)
                if intents:
                    self.process_intents(intents, now)
            except Exception as exc:  # noqa: BLE001
                self._strategy_errors[s.name] = \
                    self._strategy_errors.get(s.name, 0) + 1
                log.exception("strategy %s failed on book tick", s.name)
                if self._strategy_errors[s.name] == 1:  # don't spam the log table
                    self.store.insert_decision(now, s.name, "strategy_error", {
                        "error": f"{type(exc).__name__}: {exc}"})

    def on_trade(self, trade) -> None:
        if hasattr(self.backend, "on_trade"):
            self.backend.on_trade(trade.token_id, trade.price, trade.size,
                                  trade.ts)

    def register_market(self, market: Market) -> None:
        self.markets[market.condition_id] = market
        self._token_market[market.token_id_yes] = market
        self._token_market[market.token_id_no] = market
        if hasattr(self.backend, "register_market"):
            self.backend.register_market(market)

    def startup_reconcile(self, now: float) -> None:
        """A fresh process has no in-memory orders; anything still marked
        working in the store is an orphan from a previous run. Expire it,
        and in live mode clear the exchange before strategies start."""
        stale = self.store.orders_by_status(
            OrderStatus.SUBMITTED.value, OrderStatus.OPEN.value,
            OrderStatus.PARTIALLY_FILLED.value)
        for o in stale:
            self.store.upsert_order(o.model_copy(update={
                "status": OrderStatus.EXPIRED, "updated_ts": now}))
        if hasattr(self.backend, "reconcile_with_api"):  # live backend
            self.router.cancel_all(now)
        if stale:
            log.warning("expired %d orphaned orders from a previous run",
                        len(stale))
            self.store.insert_decision(now, "orchestrator", "startup_reconcile",
                                       {"expired_stale_orders": len(stale)})

    # -- housekeeping ----------------------------------------------------------------------
    def heartbeat(self) -> None:
        if self.heartbeat_path:
            self.heartbeat_path.write_text(str(time.time()))

    def snapshot_equity(self, now: float) -> None:
        eq = self.equity()
        self.store.insert_equity_snapshot(ts=now, equity=eq, cash=self.cash,
                                          mode=self.cfg.mode)
        verdict = self.bankroll.check(eq)
        if verdict != RunVerdict.CONTINUE and not self.halted:
            self.halt(f"bankroll verdict: {verdict}", now)

    def halt(self, reason: str, now: float) -> None:
        if self.halted:
            return
        self.halted = True
        self.stop_reason = reason
        log.warning("HALT: %s", reason)
        self.store.insert_decision(now, "orchestrator", "halt",
                                   {"reason": reason})
        self.router.cancel_all(now)

    def shutdown(self, now: Optional[float] = None) -> None:
        if self._shutdown_done:
            return
        self._shutdown_done = True
        now = now if now is not None else time.time()
        self.router.cancel_all(now)
        self.store.insert_decision(now, "orchestrator", "shutdown", {})

    # -- async main loop ---------------------------------------------------------------------
    async def update_crypto_spot(self) -> None:
        if self.coinbase is None:
            return
        for s in self.strategies:
            if s.name != "s3_crypto":
                continue
            for pair, asset in (("BTC-USD", "BTC"), ("ETH-USD", "ETH")):
                try:
                    candles = await self.coinbase.candles(pair, granularity=60)
                except Exception as exc:  # noqa: BLE001
                    log.warning("coinbase %s failed: %s", pair,
                                type(exc).__name__)
                    continue
                vol = ewma_vol_annualized(candles)
                if candles and vol:
                    s.update_spot(asset, candles[-1][1], vol_annualized=vol)

    async def refresh_markets(self) -> None:
        if self.gamma is None:
            return
        try:
            active = await self.gamma.active_markets(max_pages=4)
        except Exception as exc:  # noqa: BLE001
            log.warning("market refresh failed: %s", type(exc).__name__)
            return
        active.sort(key=lambda m: -m.volume_24h)
        for m in active[: self.cfg.max_tracked_markets]:
            self.register_market(m)
            self.store.upsert_market(m)
        if self.feed is not None:
            tokens = []
            for m in list(self.markets.values()):
                tokens += [m.token_id_yes, m.token_id_no]
            self.feed.set_assets(tokens)

    async def check_resolutions(self) -> None:
        if self.gamma is None:
            return
        try:
            resolved = await self.gamma.resolved_markets(max_pages=2)
        except Exception as exc:  # noqa: BLE001
            log.warning("resolution check failed: %s", type(exc).__name__)
            return
        now = time.time()
        for market, winner in resolved:
            if market.condition_id not in self.markets:
                continue
            self.store.set_resolution(market.condition_id, winner, now)
            if hasattr(self.backend, "settle"):
                self.backend.settle(market.condition_id, winner, now)
            for s in self.strategies:
                if hasattr(s, "on_market_resolved"):
                    s.on_market_resolved(market.condition_id)
            self.markets.pop(market.condition_id, None)
            self._token_market.pop(market.token_id_yes, None)
            self._token_market.pop(market.token_id_no, None)

    async def run(self) -> None:
        log.info("orchestrator starting in %s mode, bankroll %.2f",
                 self.cfg.mode, self.cfg.bankroll)
        self.startup_reconcile(time.time())
        if self.feed is not None:
            self.feed.cache.on_book = self.on_book
            self.feed.cache.on_trade = self.on_trade
            asyncio.create_task(self.feed.run())
        await self.refresh_markets()
        await self.update_crypto_spot()

        last_refresh = last_spot = last_resolution = last_reweight = time.time()
        try:
            while not (self.halted and self.stop_reason
                       and self.stop_reason.startswith("bankroll")):
                now = time.time()
                self.heartbeat()
                self.snapshot_equity(now)
                self.allocator.update_gates(now)
                if now - last_spot > 60:
                    await self.update_crypto_spot()
                    last_spot = now
                if now - last_refresh > self.cfg.market_refresh_seconds:
                    await self.refresh_markets()
                    last_refresh = now
                if now - last_resolution > 600:
                    await self.check_resolutions()
                    last_resolution = now
                if now - last_reweight > 7 * 86_400:
                    self.allocator.reweight(now)
                    last_reweight = now
                await asyncio.sleep(self.cfg.poll_seconds)
        finally:
            self.shutdown()
