"""
Gemini prediction-markets adapter.

Yields MarketRecord objects. Pure: fetch → yield. No DB writes here.

API facts (verified live 2026-06-12 — see tests/fixtures/gemini_events_page.json
and https://developer.gemini.com/rest-api/prediction-markets/events):
  - GET https://api.gemini.com/v1/prediction-markets/events?status=active&limit=N&offset=M
    Public, no auth for reads. Envelope: {"data": [events], "pagination":
    {limit, offset, total}}. Limit ceiling 500.
  - An EVENT (the question) holds one or more CONTRACTS (the tradable YES/NO
    instruments) → one MarketRecord per contract, like Kalshi tickers under an
    event. `instrumentSymbol` (GEMI-...) is the globally unique contract id.
  - SETTLEMENT TEXT: contract `description` is a rich-text tree
    ({data, content: [{value: "..."}]}) holding the actual resolution criteria
    ("Source Agencies, in order, are ..."). Flatten it verbatim → raw_rules,
    plus the event's structured `sourceDetails` (agency/index) when present.
    There is no separate plain rules field; full T&C live behind
    `termsAndConditionsUrl` (kept in raw_payload, not fetched).
  - raw_rules is built ONLY from stable fields (description, sourceDetails) so
    hash-based change detection doesn't see churn from prices/volume.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Iterator, Optional

import requests

from ingest.core import MarketRecord

logger = logging.getLogger(__name__)

BASE_URL = "https://api.gemini.com/v1/prediction-markets"
PAGE_DELAY_S = 0.2

_session: Optional[requests.Session] = None


def _get_session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({"Accept": "application/json"})
    return _session


def fetch_markets(status: str = "open", max_pages: int | None = None,
                  page_limit: int = 100) -> Iterator[MarketRecord]:
    """Paginate /events and yield one MarketRecord per contract."""
    api_status = "active" if status == "open" else "settled"
    session = _get_session()
    offset = 0
    page = 0

    while max_pages is None or page < max_pages:
        params = {"status": api_status, "limit": page_limit, "offset": offset}
        resp = session.get(f"{BASE_URL}/events", params=params, timeout=30)
        resp.raise_for_status()
        body = resp.json()
        events = body.get("data") or []

        if not events:
            break

        for event in events:
            try:
                yield from _to_records(event)
            except Exception as exc:  # noqa: BLE001 — one bad event must not kill the batch
                logger.warning("skipping malformed Gemini event %s: %s",
                               event.get("id", "?"), exc)

        page += 1
        offset += len(events)
        total = (body.get("pagination") or {}).get("total")
        if total is not None and offset >= total:
            break
        if len(events) < page_limit:
            break  # short page → no more data
        time.sleep(PAGE_DELAY_S)


def _to_records(event: dict) -> Iterator[MarketRecord]:
    """One MarketRecord per contract. Raises if the event has no contracts
    with identifiers (caller logs and skips)."""
    contracts = event["contracts"]
    event_context = {k: v for k, v in event.items() if k != "contracts"}

    for contract in contracts:
        venue_market_id = contract.get("instrumentSymbol") or str(contract["id"])
        label = contract.get("label") or ""
        title = event.get("title", "")
        if label and label.lower() != title.lower():
            title = f"{title} — {label}"

        yield MarketRecord(
            venue_code="gemini",
            venue_market_id=venue_market_id,
            title=title,
            raw_rules=_build_raw_rules(event, contract),
            category=event.get("category"),
            opened_at=_parse_iso(contract.get("effectiveDate")
                                 or event.get("effectiveDate")),
            closes_at=_parse_iso(contract.get("expiryDate")
                                 or event.get("expiryDate")),
            resolved_at=_parse_iso(event.get("resolvedAt")),
            outcome=_outcome(contract),
            status=_status(event, contract),
            raw_payload={"event": event_context, "contract": contract},
        )


def _build_raw_rules(event: dict, contract: dict) -> str:
    """Verbatim settlement semantics from stable fields only."""
    parts = []
    rules_text = _flatten_rich_text(contract.get("description"))
    if rules_text:
        parts.append(rules_text)
    event_desc = event.get("description")
    if isinstance(event_desc, str) and event_desc and event_desc not in rules_text:
        parts.append(f"Event: {event_desc}")
    source = event.get("sourceDetails")
    if source:
        agency = source.get("agency", "")
        index = source.get("index", "")
        parts.append(f"Settlement source: agency={agency} index={index}")
    strike = contract.get("strike")
    if strike:
        parts.append(f"Strike: value={strike.get('value')} type={strike.get('type')}")
    return "\n".join(parts)


def _flatten_rich_text(node) -> str:
    """Flatten Gemini's rich-text tree ({content: [{value, content}]}) to plain
    text, depth-first, preserving block order."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    lines: list[str] = []

    def walk(n) -> None:
        if isinstance(n, dict):
            value = n.get("value")
            if isinstance(value, str) and value.strip():
                lines.append(value)
            for child in n.get("content") or []:
                walk(child)
        elif isinstance(n, list):
            for child in n:
                walk(child)

    walk(node)
    return "\n".join(lines).strip()


def _status(event: dict, contract: dict) -> str:
    event_status = event.get("status", "")
    if event_status == "settled":
        return "resolved"
    if event_status == "invalid":
        return "voided"
    if contract.get("marketState") == "open":
        return "open"
    return "closed"


def _outcome(contract: dict) -> Optional[str]:
    side = contract.get("resolutionSide")
    if side in ("yes", "no"):
        return side.upper()
    return None


def _parse_iso(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
