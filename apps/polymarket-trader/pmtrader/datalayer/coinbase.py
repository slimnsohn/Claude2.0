"""Coinbase Exchange public market data — crypto spot for S3 fair value.

(Binance.com is geo-blocked from US IPs; Coinbase Exchange is not.)
Candles: GET /products/{pair}/candles?granularity=60
  -> [[time, low, high, open, close, volume], ...] NEWEST FIRST.
"""
from __future__ import annotations

from typing import Optional

import httpx

from pmtrader.datalayer.http_base import get_json

COINBASE_BASE = "https://api.exchange.coinbase.com"


class CoinbaseClient:
    def __init__(self, http: Optional[httpx.AsyncClient] = None,
                 base: str = COINBASE_BASE, retry_base_delay: float = 0.5):
        self.http = http or httpx.AsyncClient(timeout=30)
        self.base = base
        self.retry_base_delay = retry_base_delay

    async def close(self) -> None:
        await self.http.aclose()

    async def candles(self, pair: str = "BTC-USD",
                      granularity: int = 60) -> list[tuple[float, float]]:
        """Returns [(ts, close), ...] OLDEST FIRST."""
        raw = await get_json(self.http, f"{self.base}/products/{pair}/candles",
                             {"granularity": granularity},
                             base_delay=self.retry_base_delay)
        out = [(float(c[0]), float(c[4])) for c in raw]
        out.sort(key=lambda x: x[0])
        return out

    async def spot(self, pair: str = "BTC-USD") -> float:
        raw = await get_json(self.http, f"{self.base}/products/{pair}/ticker",
                             base_delay=self.retry_base_delay)
        return float(raw["price"])
