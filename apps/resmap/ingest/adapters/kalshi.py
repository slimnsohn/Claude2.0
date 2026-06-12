"""
Kalshi adapter.

Yields MarketRecord objects. Pure: fetch → yield. No DB writes here.

API facts (verified live 2026-06-12; RSA-PSS auth proven in the old
resolution-mismatch-detector):
  - GET /markets is PUBLIC — market data needs no credentials. RSA-PSS signing
    (sign "{timestamp_ms}{METHOD}{path}", SHA-256, MGF1(SHA-256), salt 32;
    headers KALSHI-ACCESS-KEY / -SIGNATURE / -TIMESTAMP) is only required for
    private endpoints, so the adapter signs when creds are configured and runs
    unsigned otherwise.
  - Base: https://api.elections.kalshi.com/trade-api/v2. Cursor pagination on
    GET /markets?market_status=active&limit=100. 429 → exponential backoff,
    re-sign on retry (timestamp changes).
  - Identifiers: market `ticker` is the venue_market_id.
  - SETTLEMENT TEXT: rules_primary + rules_secondary, verbatim. Kalshi is more
    explicit than Polymarket about the authoritative source — good for the
    `sources` normalization downstream.

Env (optional — see .env.example): KALSHI_API_KEY_ID, KALSHI_PRIVATE_KEY_PATH.
"""
from __future__ import annotations

import base64
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional
from urllib.parse import urlparse

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from ingest.core import MarketRecord

logger = logging.getLogger(__name__)

BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
PAGE_DELAY_S = 1.0


class KalshiSession:
    """Request session, signed when credentials are configured. Separated from
    fetch_markets so signing and retry logic are unit-testable with a
    throwaway in-test RSA key."""

    def __init__(self, key_id: str | None = None,
                 private_key_pem: bytes | None = None):
        self.key_id = key_id or None
        self._private_key = (
            serialization.load_pem_private_key(private_key_pem, password=None)
            if private_key_pem else None)
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

    @classmethod
    def from_env(cls) -> "KalshiSession":
        """Signed session when KALSHI_API_KEY_ID + key file exist; unsigned
        otherwise (market data is public)."""
        key_id = os.environ.get("KALSHI_API_KEY_ID", "").strip()
        pk_path = os.environ.get("KALSHI_PRIVATE_KEY_PATH", "").strip()
        if key_id and pk_path:
            path = Path(pk_path)
            if not path.is_absolute():
                path = Path(__file__).resolve().parents[2] / pk_path
            if path.exists():
                return cls(key_id, path.read_bytes())
            logger.warning("Kalshi key file missing at %s — running unsigned", path)
        return cls()

    def sign_headers(self, method: str, path: str) -> dict:
        """Payload is "{timestamp_ms}{METHOD}{path}" with query params stripped
        — matches Kalshi's reference implementation exactly. Empty dict in
        unsigned mode (public market data)."""
        if not self._private_key or not self.key_id:
            return {}
        timestamp_ms = str(int(time.time() * 1000))
        clean_path = path.split("?")[0]
        payload = f"{timestamp_ms}{method.upper()}{clean_path}"
        signature = self._private_key.sign(
            payload.encode("utf-8"),
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32),
            hashes.SHA256(),
        )
        return {
            "KALSHI-ACCESS-KEY": self.key_id,
            "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode("utf-8"),
            "KALSHI-ACCESS-TIMESTAMP": timestamp_ms,
        }

    def request(self, method: str, url: str, max_retries: int = 3,
                backoff: float = 2.0, **kwargs) -> requests.Response:
        path = urlparse(url).path
        for attempt in range(max_retries + 1):
            headers = kwargs.pop("headers", {}) or {}
            headers.update(self.sign_headers(method, path))  # re-sign every try
            resp = self.session.request(method, url, headers=headers,
                                        timeout=30, **kwargs)
            if resp.status_code == 429 and attempt < max_retries:
                wait = backoff * (2 ** attempt)
                logger.warning("Kalshi 429 — retrying in %.1fs", wait)
                time.sleep(wait)
                continue
            if resp.status_code >= 400:
                logger.error("Kalshi %d: %s", resp.status_code, resp.text[:500])
            resp.raise_for_status()
            return resp
        raise requests.exceptions.RetryError("max retries exceeded on 429")


def fetch_markets(status: str = "open", max_pages: int | None = None,
                  page_limit: int = 100,
                  session: KalshiSession | None = None,
                  min_close_days: float | None = 1.0) -> Iterator[MarketRecord]:
    """Cursor-paginate /markets and yield one MarketRecord per market.

    min_close_days (default 1.0) maps to the API's min_close_ts: Kalshi's
    feed is dominated by auto-generated same-day multi-leg parlays with NO
    rules text (verified live: 30k of the first 30k cursor results). They are
    worthless for a resolution-semantics dataset and drown out real markets.
    Pass None to include them."""
    sess = session or KalshiSession.from_env()
    api_status = "active" if status == "open" else "settled"
    cursor = None
    page = 0

    while max_pages is None or page < max_pages:
        params = {"market_status": api_status, "limit": page_limit}
        if min_close_days is not None and status == "open":
            params["min_close_ts"] = int(time.time() + min_close_days * 86400)
        if cursor:
            params["cursor"] = cursor
        resp = sess.request("GET", f"{BASE_URL}/markets", params=params)
        data = resp.json()
        raw_markets = data.get("markets") or []

        for raw in raw_markets:
            try:
                yield _to_record(raw)
            except Exception as exc:  # noqa: BLE001 — one bad market must not kill the batch
                logger.warning("skipping malformed Kalshi market %s: %s",
                               raw.get("ticker", "?"), exc)

        page += 1
        cursor = data.get("cursor")
        if not cursor or not raw_markets:
            break
        time.sleep(PAGE_DELAY_S)


def _to_record(raw: dict) -> MarketRecord:
    rules_primary = raw.get("rules_primary") or ""
    rules_secondary = raw.get("rules_secondary") or ""
    parts = [p for p in (rules_primary, rules_secondary) if p]
    # Kalshi's explicit settlement source feeds the `sources` table downstream
    settlement_sources = raw.get("settlement_sources")
    if settlement_sources:
        if isinstance(settlement_sources, list):
            names = ", ".join(
                s.get("name", str(s)) if isinstance(s, dict) else str(s)
                for s in settlement_sources)
        else:
            names = str(settlement_sources)
        parts.append(f"Settlement source: {names}")

    return MarketRecord(
        venue_code="kalshi",
        venue_market_id=raw["ticker"],
        title=raw.get("title", ""),
        raw_rules="\n".join(parts),
        category=raw.get("category"),
        opened_at=_parse_iso(raw.get("open_time")),
        closes_at=_parse_iso(raw.get("close_time")),
        resolved_at=_parse_iso(raw.get("settled_time")),
        outcome=_outcome(raw),
        status=_status(raw),
        raw_payload=raw,
    )


def _status(raw: dict) -> str:
    s = (raw.get("status") or "").lower()
    if s in ("settled", "finalized"):
        return "resolved"
    if s == "active":
        return "open"
    return "closed"


def _outcome(raw: dict) -> Optional[str]:
    result = (raw.get("result") or "").lower()
    if result in ("yes", "no"):
        return result.upper()
    return None


def _parse_iso(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
