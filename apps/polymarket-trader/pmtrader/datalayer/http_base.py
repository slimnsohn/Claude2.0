"""Shared retrying HTTP GET used by all REST clients."""
from __future__ import annotations

import asyncio

import httpx

from pmtrader.datalayer.errors import DataError

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


async def get_json(http: httpx.AsyncClient, url: str, params: dict | None = None,
                   retries: int = 3, base_delay: float = 0.5):
    last: str = "no attempt"
    for attempt in range(retries + 1):
        try:
            r = await http.get(url, params=params)
            if r.status_code in RETRYABLE_STATUS:
                last = f"HTTP {r.status_code}"
            else:
                r.raise_for_status()
                return r.json()
        except httpx.HTTPStatusError as exc:
            raise DataError(f"GET {url}: HTTP {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            last = f"{type(exc).__name__}: {exc}"
        if attempt < retries:
            await asyncio.sleep(base_delay * (4 ** attempt))
    raise DataError(f"GET {url} failed after {retries + 1} attempts: {last}")
