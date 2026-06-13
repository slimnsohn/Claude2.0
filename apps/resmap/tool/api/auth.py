"""
API-key auth + in-memory rate limiting for the read-only product surface.

Keys live in the `api_keys` table (per-key requests/minute). The limiter is a
process-local sliding window — fine for a single-instance demo; swap for Redis
if the API is ever horizontally scaled.
"""
from __future__ import annotations

import hashlib
import time
from typing import Callable, Optional


def hash_key(raw_key: str) -> str:
    """SHA-256 hex of a raw API key. Only the hash is stored, so a DB leak
    never exposes usable keys."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


class RateLimiter:
    """Sliding-window request counter, keyed by API key. `clock` is injectable
    so the window is deterministic in tests."""

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._hits: dict[str, list[float]] = {}
        self._clock = clock

    def allow(self, key: str, limit: int, window: float = 60.0) -> bool:
        now = self._clock()
        hits = [t for t in self._hits.get(key, []) if now - t < window]
        if len(hits) >= limit:
            self._hits[key] = hits
            return False
        hits.append(now)
        self._hits[key] = hits
        return True

    def reset(self) -> None:
        self._hits.clear()


def lookup_key(conn, raw_key: str) -> Optional[dict]:
    """Return {key_hash, label, rate_per_min} for an active key, else None.
    The raw key is hashed before lookup — only hashes are stored."""
    if not raw_key:
        return None
    with conn.cursor() as cur:
        cur.execute(
            "SELECT key_hash, label, rate_per_min FROM api_keys "
            "WHERE key_hash = %s AND active = TRUE",
            (hash_key(raw_key),),
        )
        row = cur.fetchone()
    if not row:
        return None
    return {"key_hash": row[0], "label": row[1], "rate_per_min": row[2]}
