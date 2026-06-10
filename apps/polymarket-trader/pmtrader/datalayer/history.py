"""Historical data fetcher: resolved + active markets, price history per token.

Resumable: a checkpoint row per token marks completed fetches so re-runs only
pull what's missing. Polite rate limiting; errors skip the token, not the run.
"""
from __future__ import annotations

import asyncio
import logging
import time

from pmtrader.datalayer.clob_rest import ClobRestClient
from pmtrader.datalayer.errors import DataError
from pmtrader.datalayer.gamma import GammaClient
from pmtrader.datalayer.store import Store

log = logging.getLogger(__name__)


class HistoryFetcher:
    def __init__(self, store: Store, gamma: GammaClient, clob: ClobRestClient,
                 rate_limit_per_s: float = 5.0, fidelity: int = 60):
        self.store = store
        self.gamma = gamma
        self.clob = clob
        self.min_interval = 1.0 / rate_limit_per_s
        self.fidelity = fidelity
        self._last_call = 0.0

    async def _throttle(self) -> None:
        wait = self._last_call + self.min_interval - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_call = time.monotonic()

    async def run(self, resolved_since: str = "2024-01-01",
                  max_markets: int = 10_000, include_active: bool = True) -> dict:
        stats = {"markets": 0, "tokens_fetched": 0, "tokens_skipped": 0, "errors": 0}
        targets = []
        # Gamma caps offset pagination ~10k rows; bound pages to what we need.
        pages = max(1, -(-max_markets // 100))

        resolved = await self.gamma.resolved_markets(end_date_min=resolved_since,
                                                     max_pages=pages)
        for market, winner in resolved:
            self.store.upsert_market(market)
            self.store.set_resolution(market.condition_id, winner, time.time())
            targets.append(market)

        if include_active:
            for market in await self.gamma.active_markets(max_pages=pages):
                self.store.upsert_market(market)
                targets.append(market)

        targets = targets[:max_markets]
        stats["markets"] = len(targets)

        for n, market in enumerate(targets):
            for token_id in (market.token_id_yes, market.token_id_no):
                key = f"hist:{token_id}:{self.fidelity}"
                done = self.store.get_checkpoint(key)
                if done is not None and done != "0":
                    stats["tokens_skipped"] += 1
                    continue
                points: list[tuple[float, float]] = []
                try:
                    # CLOB serves fine fidelity only for recent data; fall back
                    # to daily for older/closed markets rather than losing them.
                    for fidelity in (self.fidelity, 1440):
                        await self._throttle()
                        points = await self.clob.prices_history(token_id, fidelity=fidelity)
                        if points:
                            break
                except DataError as exc:
                    log.warning("history fetch failed for %s: %s", token_id, exc)
                    stats["errors"] += 1
                    continue
                self.store.insert_price_history(token_id, points)
                self.store.set_checkpoint(key, str(len(points)))
                stats["tokens_fetched"] += 1
            if n and n % 50 == 0:
                log.info("history: %d/%d markets done", n, len(targets))
        return stats
