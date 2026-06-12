"""
Polymarket adapter.

Yields MarketRecord objects. Pure: fetch → yield. No DB writes here.

Gamma API facts (verified live 2026-06-12 — see tests/fixtures/gamma_markets_page.json):
  - GET https://gamma-api.polymarket.com/markets?active=true&closed=false&limit=100&offset=N
    No key needed for public reads. Page cap is 100. A short page means no more data.
  - Keys are camelCase: `conditionId`, `endDate`, `startDate`. `outcomes` /
    `outcomePrices` arrive as JSON-encoded *strings*, not arrays (we don't need
    them — prices are a commodity; we store rules).
  - SETTLEMENT TEXT: the `description` field IS the resolution criteria. It is
    usually plain text but can contain HTML — strip tags, keep structure.
  - `conditionId` is the stable identifier (venue_market_id); numeric `id` is a
    fallback for legacy rows that lack it.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from typing import Iterator, Optional

import requests

from ingest.core import MarketRecord

logger = logging.getLogger(__name__)

GAMMA_BASE_URL = "https://gamma-api.polymarket.com"
PAGE_DELAY_S = 0.2

_session: Optional[requests.Session] = None


def _get_session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate",  # avoid brotli decoding issues
        })
    return _session


def fetch_markets(status: str = "open", max_pages: int | None = None,
                  page_limit: int = 100) -> Iterator[MarketRecord]:
    """Paginate the Gamma API and yield one MarketRecord per market.

    No volume/category filtering here — the registry layer wants completeness;
    parse-cost prioritization happens downstream (parse/rule_parser.py).
    """
    if status == "open":
        base_params = {"active": "true", "closed": "false"}
    else:
        base_params = {"closed": "true"}
    # Highest-volume first: Gamma rejects offsets past ~10k (422), so the
    # reachable window must contain the markets that matter most.
    base_params.update({"order": "volumeNum", "ascending": "false"})

    session = _get_session()
    offset = 0
    page = 0

    while max_pages is None or page < max_pages:
        params = {**base_params, "limit": page_limit, "offset": offset}
        resp = session.get(f"{GAMMA_BASE_URL}/markets", params=params, timeout=30)
        if resp.status_code == 422:
            # offset cap reached — end of the reachable window, not an error
            logger.warning("Gamma offset cap hit at offset=%d — stopping", offset)
            break
        resp.raise_for_status()
        page_data = resp.json()

        if not page_data:
            break

        for raw in page_data:
            try:
                yield _to_record(raw)
            except Exception as exc:  # noqa: BLE001 — one bad market must not kill the batch
                logger.warning("skipping malformed Polymarket market %s: %s",
                               raw.get("id", "?"), exc)

        page += 1
        if len(page_data) < page_limit:
            break  # short page → no more data
        offset += page_limit
        time.sleep(PAGE_DELAY_S)


def _to_record(raw: dict) -> MarketRecord:
    venue_market_id = raw.get("conditionId") or str(raw["id"])
    return MarketRecord(
        venue_code="polymarket",
        venue_market_id=venue_market_id,
        title=raw.get("question", ""),
        raw_rules=_strip_html(raw.get("description", "")),
        category=raw.get("category"),
        opened_at=_parse_iso(raw.get("startDate")),
        closes_at=_parse_iso(raw.get("endDate")),
        status="open" if raw.get("active") in (True, None) and not raw.get("closed")
               else "closed",
        raw_payload=raw,
    )


def _parse_iso(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _strip_html(text: str) -> str:
    """Strip HTML tags while preserving newlines and bullet structure.
    Ported verbatim from the proven resolution-mismatch-detector implementation."""
    if not text:
        return ""

    # Convert block-level elements to newlines
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</(?:p|div|h[1-6]|tr)>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<li[^>]*>", "- ", text, flags=re.IGNORECASE)
    text = re.sub(r"</li>", "\n", text, flags=re.IGNORECASE)

    # Strip remaining tags
    text = re.sub(r"<[^>]+>", "", text)

    # Decode common HTML entities
    text = text.replace("&amp;", "&")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    text = text.replace("&quot;", '"')
    text = text.replace("&#39;", "'")
    text = text.replace("&nbsp;", " ")

    # Collapse excessive blank lines but preserve intentional structure
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
