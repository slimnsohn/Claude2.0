"""CLOB market-channel WSS consumer.

Frame types confirmed by recorded tape (tests/fixtures/wss_market_sample.jsonl):
- "book": full snapshot {asset_id, bids, asks, timestamp(ms)} — replaces book
- "price_change": {price_changes: [{asset_id, price, size, side}]} — level
  updates; size 0 removes the level
- "last_trade_price": trade print {asset_id, price, size, side, timestamp}
- "tick_size_change": ignored for the cache

The feed auto-reconnects with backoff and re-subscribes; consumers watch
seconds_since_message() for staleness (risk manager refuses stale books).
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Callable, Optional

import websockets

from pmtrader.core.models import Level, OrderBook, Side

log = logging.getLogger(__name__)

WSS_MARKET_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"


@dataclass
class TradePrint:
    token_id: str
    price: float
    size: float
    side: Side
    ts: float


class BookCache:
    def __init__(self):
        self.books: dict[str, OrderBook] = {}
        self.on_book: Optional[Callable[[OrderBook], None]] = None
        self.on_trade: Optional[Callable[[TradePrint], None]] = None

    def apply(self, frame: dict) -> None:
        et = frame.get("event_type")
        if et == "book":
            self._apply_snapshot(frame)
        elif et == "price_change":
            self._apply_changes(frame)
        elif et == "last_trade_price":
            self._apply_trade(frame)
        # tick_size_change and unknown events are intentionally ignored

    @staticmethod
    def _ts(frame: dict) -> float:
        try:
            return int(frame.get("timestamp", 0)) / 1000
        except (TypeError, ValueError):
            return time.time()

    def _apply_snapshot(self, frame: dict) -> None:
        token_id = frame["asset_id"]
        book = OrderBook(
            token_id=token_id, ts=self._ts(frame),
            bids=[Level(price=float(l["price"]), size=float(l["size"]))
                  for l in frame.get("bids", []) if 0 < float(l["price"]) < 1],
            asks=[Level(price=float(l["price"]), size=float(l["size"]))
                  for l in frame.get("asks", []) if 0 < float(l["price"]) < 1])
        self.books[token_id] = book
        if self.on_book:
            self.on_book(book)

    def _apply_changes(self, frame: dict) -> None:
        ts = self._ts(frame)
        touched = set()
        for ch in frame.get("price_changes", []):
            token_id = ch["asset_id"]
            book = self.books.get(token_id)
            if book is None:
                continue  # no snapshot yet; wait for one
            price, size = float(ch["price"]), float(ch["size"])
            side_levels = book.bids if ch.get("side") == "BUY" else book.asks
            side_levels[:] = [l for l in side_levels if abs(l.price - price) > 1e-9]
            if size > 0 and 0 < price < 1:
                side_levels.append(Level(price=price, size=size))
            touched.add(token_id)
        for token_id in touched:
            book = self.books[token_id]
            self.books[token_id] = OrderBook(token_id=token_id, ts=ts,
                                             bids=book.bids, asks=book.asks)
            if self.on_book:
                self.on_book(self.books[token_id])

    def _apply_trade(self, frame: dict) -> None:
        if self.on_trade is None:
            return
        try:
            self.on_trade(TradePrint(
                token_id=frame["asset_id"],
                price=float(frame["price"]),
                size=float(frame.get("size", 0.0)),
                side=Side(frame.get("side", "BUY")),
                ts=self._ts(frame)))
        except (KeyError, ValueError):
            log.warning("unparseable trade frame: %s", str(frame)[:200])


class ClobMarketFeed:
    def __init__(self, assets: list[str], url: str = WSS_MARKET_URL,
                 reconnect_delay: float = 1.0, max_reconnect_delay: float = 30.0,
                 stale_after: float = 30.0):
        self.url = url
        self.assets = list(assets)
        self.reconnect_delay = reconnect_delay
        self.max_reconnect_delay = max_reconnect_delay
        self.stale_after = stale_after
        self.cache = BookCache()
        self._last_msg: Optional[float] = None
        self._running = False

    def seconds_since_message(self) -> Optional[float]:
        if self._last_msg is None:
            return None
        return time.monotonic() - self._last_msg

    def is_stale(self) -> bool:
        age = self.seconds_since_message()
        return age is None or age > self.stale_after

    def set_assets(self, assets: list[str]) -> None:
        """Takes effect on next (re)connect."""
        self.assets = list(assets)

    async def run(self) -> None:
        self._running = True
        delay = self.reconnect_delay
        while self._running:
            try:
                async with websockets.connect(self.url, open_timeout=15) as ws:
                    await ws.send(json.dumps(
                        {"assets_ids": self.assets, "type": "market"}))
                    delay = self.reconnect_delay  # successful connect resets backoff
                    async for raw in ws:
                        self._last_msg = time.monotonic()
                        try:
                            msgs = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(msgs, dict):
                            msgs = [msgs]
                        for frame in msgs:
                            self.cache.apply(frame)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — feed must outlive any error
                log.warning("market feed dropped: %s: %s",
                            type(exc).__name__, exc)
            if self._running:
                await asyncio.sleep(delay)
                delay = min(delay * 2, self.max_reconnect_delay)

    def stop(self) -> None:
        self._running = False
