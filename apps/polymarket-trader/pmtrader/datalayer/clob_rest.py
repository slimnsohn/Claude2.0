"""CLOB REST client — order books and price history (public, no auth).

Field semantics confirmed by recon 2026-06-09: book levels are
{price: str, size: str} sorted worst-first; timestamp is epoch ms;
prices-history returns {history: [{t: epoch_s, p: float}, ...]}.
"""
from __future__ import annotations

from typing import Optional

import httpx

from pmtrader.core.models import Level, OrderBook
from pmtrader.datalayer.http_base import get_json

CLOB_BASE = "https://clob.polymarket.com"


class ClobRestClient:
    def __init__(self, http: Optional[httpx.AsyncClient] = None,
                 base: str = CLOB_BASE, retry_base_delay: float = 0.5):
        self.http = http or httpx.AsyncClient(timeout=30)
        self.base = base
        self.retry_base_delay = retry_base_delay

    async def close(self) -> None:
        await self.http.aclose()

    async def book(self, token_id: str) -> OrderBook:
        raw = await get_json(self.http, f"{self.base}/book", {"token_id": token_id},
                             base_delay=self.retry_base_delay)
        return OrderBook(
            token_id=token_id,
            ts=int(raw.get("timestamp", 0)) / 1000,
            bids=[Level(price=float(l["price"]), size=float(l["size"]))
                  for l in raw.get("bids", []) if 0 < float(l["price"]) < 1],
            asks=[Level(price=float(l["price"]), size=float(l["size"]))
                  for l in raw.get("asks", []) if 0 < float(l["price"]) < 1],
        )

    async def prices_history(self, token_id: str, interval: str = "max",
                             fidelity: int = 60) -> list[tuple[float, float]]:
        raw = await get_json(self.http, f"{self.base}/prices-history", {
            "market": token_id, "interval": interval, "fidelity": fidelity},
            base_delay=self.retry_base_delay)
        return [(pt["t"], pt["p"]) for pt in raw.get("history", [])]
