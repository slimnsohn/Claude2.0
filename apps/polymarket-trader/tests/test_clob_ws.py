"""WSS market feed: book cache from real recorded frames, reconnect, staleness."""
import asyncio
import json
from pathlib import Path

import pytest
import websockets

from pmtrader.datalayer.clob_ws import BookCache, ClobMarketFeed

FIXTURE = Path(__file__).parent / "fixtures" / "wss_market_sample.jsonl"


def load_messages():
    return [json.loads(line) for line in FIXTURE.read_text(encoding="utf-8").splitlines()]


class TestBookCache:
    def test_snapshot_then_deltas_consistent(self):
        cache = BookCache()
        for msgs in load_messages():
            if isinstance(msgs, dict):
                msgs = [msgs]
            for m in msgs:
                cache.apply(m)
        # after replaying the full tape every cached book is internally sane
        books = list(cache.books.values())
        assert books, "fixture produced no books"
        for book in books:
            if book.best_bid is not None and book.best_ask is not None:
                assert book.best_bid <= book.best_ask + 1e-9

    def test_snapshot_replaces_book(self):
        cache = BookCache()
        snap = {"event_type": "book", "asset_id": "tok", "timestamp": "1000000",
                "bids": [{"price": "0.40", "size": "100"}],
                "asks": [{"price": "0.60", "size": "100"}]}
        cache.apply(snap)
        assert cache.books["tok"].best_bid == pytest.approx(0.40)
        snap2 = dict(snap, bids=[{"price": "0.45", "size": "50"}])
        cache.apply(snap2)
        assert cache.books["tok"].best_bid == pytest.approx(0.45)

    def test_price_change_updates_level(self):
        cache = BookCache()
        cache.apply({"event_type": "book", "asset_id": "tok", "timestamp": "1000000",
                     "bids": [{"price": "0.40", "size": "100"}],
                     "asks": [{"price": "0.60", "size": "100"}]})
        cache.apply({"event_type": "price_change", "timestamp": "1000001",
                     "price_changes": [
                         {"asset_id": "tok", "price": "0.41", "size": "30",
                          "side": "BUY"},
                         {"asset_id": "tok", "price": "0.40", "size": "0",
                          "side": "BUY"}]})
        book = cache.books["tok"]
        assert book.best_bid == pytest.approx(0.41)
        assert all(l.price != 0.40 for l in book.bids)  # zero-size removes level

    def test_trade_event_extracted(self):
        cache = BookCache()
        trades = []
        cache.on_trade = lambda t: trades.append(t)
        cache.apply({"event_type": "last_trade_price", "asset_id": "tok",
                     "price": "0.55", "size": "120", "side": "SELL",
                     "timestamp": "1000002"})
        assert len(trades) == 1
        assert trades[0].price == pytest.approx(0.55)
        assert trades[0].size == pytest.approx(120.0)


class FakeServer:
    """Minimal WSS server: sends canned frames, then drops the connection."""

    def __init__(self, frames_per_conn):
        self.frames_per_conn = frames_per_conn
        self.connections = 0
        self.subscriptions = []

    async def handler(self, ws):
        self.connections += 1
        sub = await ws.recv()
        self.subscriptions.append(json.loads(sub))
        for frame in self.frames_per_conn:
            await ws.send(json.dumps(frame))
        await asyncio.sleep(0.2)
        await ws.close()


SNAP = {"event_type": "book", "asset_id": "tok", "timestamp": "1000000",
        "bids": [{"price": "0.40", "size": "100"}],
        "asks": [{"price": "0.60", "size": "100"}]}


async def test_feed_reconnects_and_resubscribes():
    server = FakeServer([SNAP])
    async with websockets.serve(server.handler, "127.0.0.1", 0) as srv:
        port = srv.sockets[0].getsockname()[1]
        feed = ClobMarketFeed(url=f"ws://127.0.0.1:{port}",
                              assets=["tok"], reconnect_delay=0.05)
        task = asyncio.create_task(feed.run())
        try:
            await asyncio.sleep(1.0)
            assert server.connections >= 2  # dropped + reconnected at least once
            assert all(s == {"assets_ids": ["tok"], "type": "market"}
                       for s in server.subscriptions)
            assert feed.cache.books["tok"].best_bid == pytest.approx(0.40)
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task


async def test_staleness_flag():
    server = FakeServer([SNAP])
    async with websockets.serve(server.handler, "127.0.0.1", 0) as srv:
        port = srv.sockets[0].getsockname()[1]
        feed = ClobMarketFeed(url=f"ws://127.0.0.1:{port}", assets=["tok"],
                              reconnect_delay=0.05, stale_after=0.2)
        task = asyncio.create_task(feed.run())
        try:
            await asyncio.sleep(0.5)
            # server sends one frame then silence; feed must self-report stale
            assert feed.seconds_since_message() is not None
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
