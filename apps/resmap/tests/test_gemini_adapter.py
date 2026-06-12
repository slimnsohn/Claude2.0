"""Unit tests for the Gemini prediction-markets adapter — fixture-based, no network.

The fixture is a real /v1/prediction-markets/events page captured 2026-06-12.
Gemini facts the adapter must handle:
  - Envelope is {"data": [...events], "pagination": {limit, offset, total}}.
  - An EVENT holds one or more CONTRACTS; the contract is the tradable YES/NO
    instrument → one MarketRecord per contract.
  - Contract `description` is a rich-text tree ({data, content:[{value:...}]})
    holding the actual settlement rules text — flatten it for raw_rules.
  - `instrumentSymbol` (GEMI-...) is the globally unique contract identifier.
"""
import json
from pathlib import Path

import pytest

from ingest.adapters.gemini import _flatten_rich_text, _to_records, fetch_markets
from ingest.core import MarketRecord

FIXTURE = Path(__file__).parent / "fixtures" / "gemini_events_page.json"


@pytest.fixture
def gemini_page() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


# ── _to_records: one record per contract, real payload ───────────────────────

def test_event_yields_one_record_per_contract(gemini_page):
    event = gemini_page["data"][0]
    records = list(_to_records(event))
    assert len(records) == len(event["contracts"])
    assert all(isinstance(r, MarketRecord) for r in records)


def test_record_identity_and_title(gemini_page):
    event = gemini_page["data"][0]
    rec = list(_to_records(event))[0]
    contract = event["contracts"][0]
    assert rec.venue_code == "gemini"
    assert rec.venue_market_id == contract["instrumentSymbol"]
    assert rec.venue_market_id.startswith("GEMI-")
    assert event["title"] in rec.title
    assert contract["label"] in rec.title


def test_raw_rules_contains_settlement_text(gemini_page):
    event = gemini_page["data"][0]
    rec = list(_to_records(event))[0]
    # the rich-text description holds the actual resolution criteria
    assert "resolve" in rec.raw_rules.lower()
    assert len(rec.raw_rules) > 50


def test_raw_rules_includes_source_details_when_present(gemini_page):
    event = next(e for e in gemini_page["data"] if e.get("sourceDetails"))
    rec = list(_to_records(event))[0]
    assert event["sourceDetails"]["agency"] in rec.raw_rules


def test_raw_rules_is_deterministic(gemini_page):
    """Hash-based change detection requires byte-identical re-serialization."""
    event = gemini_page["data"][0]
    a = list(_to_records(event))[0].raw_rules
    b = list(_to_records(json.loads(json.dumps(event))))[0].raw_rules
    assert a == b


def test_timestamps_and_status(gemini_page):
    event = gemini_page["data"][0]
    rec = list(_to_records(event))[0]
    assert rec.status == "open"  # fixture markets are active/open
    assert rec.closes_at is not None and rec.closes_at.tzinfo is not None
    assert rec.category == event["category"]


def test_settled_event_maps_to_resolved():
    event = {
        "id": "1", "title": "T?", "status": "settled", "category": "Econ",
        "contracts": [{
            "instrumentSymbol": "GEMI-T-YES", "label": "Yes",
            "marketState": "closed", "status": "settled",
            "resolutionSide": "yes",
            "description": {"content": [{"value": "Resolves Yes if T."}]},
        }],
    }
    rec = list(_to_records(event))[0]
    assert rec.status == "resolved"
    assert rec.outcome == "YES"


def test_raw_payload_keeps_event_context_and_full_contract(gemini_page):
    event = gemini_page["data"][0]
    rec = list(_to_records(event))[0]
    assert rec.raw_payload["contract"] == event["contracts"][0]
    assert rec.raw_payload["event"]["id"] == event["id"]
    # contracts list excluded from the event copy — each row carries its own
    assert "contracts" not in rec.raw_payload["event"]


# ── rich-text flattening ─────────────────────────────────────────────────────

def test_flatten_rich_text_nested_nodes():
    doc = {"content": [
        {"value": "Line one."},
        {"content": [{"value": "Nested line."}]},
    ]}
    out = _flatten_rich_text(doc)
    assert "Line one." in out
    assert "Nested line." in out


def test_flatten_rich_text_plain_string_passthrough():
    assert _flatten_rich_text("plain text") == "plain text"


def test_flatten_rich_text_none_is_empty():
    assert _flatten_rich_text(None) == ""


# ── fetch_markets: pagination with mocked session ────────────────────────────

class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_fetch_markets_paginates_until_total(gemini_page, monkeypatch):
    n = len(gemini_page["data"])
    pages = [
        {"data": gemini_page["data"], "pagination": {"limit": n, "offset": 0, "total": n * 2}},
        {"data": gemini_page["data"], "pagination": {"limit": n, "offset": n, "total": n * 2}},
    ]
    calls = []

    def fake_get(self, url, params=None, timeout=None):
        calls.append(dict(params))
        return _FakeResponse(pages[len(calls) - 1])

    import requests
    monkeypatch.setattr(requests.Session, "get", fake_get)
    monkeypatch.setattr("ingest.adapters.gemini.PAGE_DELAY_S", 0)

    records = list(fetch_markets(status="open", page_limit=n))
    expected = 2 * sum(len(e["contracts"]) for e in gemini_page["data"])
    assert len(records) == expected
    assert calls[0]["offset"] == 0
    assert calls[1]["offset"] == n
    assert calls[0]["status"] == "active"


def test_fetch_markets_respects_max_pages(gemini_page, monkeypatch):
    n = len(gemini_page["data"])

    def fake_get(self, url, params=None, timeout=None):
        return _FakeResponse({"data": gemini_page["data"],
                              "pagination": {"limit": n, "offset": 0, "total": 10_000}})

    import requests
    monkeypatch.setattr(requests.Session, "get", fake_get)
    monkeypatch.setattr("ingest.adapters.gemini.PAGE_DELAY_S", 0)

    records = list(fetch_markets(status="open", max_pages=1, page_limit=n))
    assert len(records) == sum(len(e["contracts"]) for e in gemini_page["data"])


def test_fetch_markets_skips_malformed_event(gemini_page, monkeypatch):
    n = len(gemini_page["data"])
    data = [{"garbage": True}] + gemini_page["data"]

    def fake_get(self, url, params=None, timeout=None):
        return _FakeResponse({"data": data,
                              "pagination": {"limit": 100, "offset": 0, "total": len(data)}})

    import requests
    monkeypatch.setattr(requests.Session, "get", fake_get)
    monkeypatch.setattr("ingest.adapters.gemini.PAGE_DELAY_S", 0)

    records = list(fetch_markets(status="open"))
    assert len(records) == sum(len(e["contracts"]) for e in gemini_page["data"])
