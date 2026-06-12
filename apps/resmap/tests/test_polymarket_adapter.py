"""Unit tests for the Polymarket adapter — fixture-based, no network.

The fixture is a real Gamma API page captured 2026-06-12. Gamma quirks the
adapter must handle (verified against the live API, NOT the old project's
assumptions): camelCase keys (conditionId, endDate, startDate), and
outcomes/outcomePrices delivered as JSON-encoded *strings*.
"""
import json
from datetime import timezone
from pathlib import Path

import pytest

from ingest.adapters.polymarket import _strip_html, _to_record, fetch_markets
from ingest.core import MarketRecord

FIXTURE = Path(__file__).parent / "fixtures" / "gamma_markets_page.json"


@pytest.fixture
def gamma_page() -> list[dict]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


# ── _to_record: field mapping against the real payload ───────────────────────

def test_to_record_maps_real_gamma_fields(gamma_page):
    rec = _to_record(gamma_page[0])
    assert isinstance(rec, MarketRecord)
    assert rec.venue_code == "polymarket"
    # conditionId (camelCase) is the stable identifier, not numeric `id`
    assert rec.venue_market_id == gamma_page[0]["conditionId"]
    assert rec.venue_market_id.startswith("0x")
    assert rec.title == gamma_page[0]["question"]
    assert rec.status == "open"


def test_to_record_captures_rules_verbatim_content(gamma_page):
    rec = _to_record(gamma_page[0])
    # description IS the settlement text; must survive into raw_rules
    assert 'resolve to "Yes"' in rec.raw_rules
    assert "resolution source" in rec.raw_rules.lower()


def test_to_record_parses_timestamps_tz_aware(gamma_page):
    rec = _to_record(gamma_page[0])
    assert rec.closes_at is not None and rec.closes_at.tzinfo is not None
    assert rec.opened_at is not None and rec.opened_at.tzinfo is not None
    assert rec.closes_at.astimezone(timezone.utc).year >= 2026


def test_to_record_keeps_full_payload_for_forensics(gamma_page):
    rec = _to_record(gamma_page[0])
    assert rec.raw_payload == gamma_page[0]


def test_to_record_falls_back_to_id_when_no_condition_id():
    raw = {"id": "12345", "question": "Q?", "description": "rules"}
    rec = _to_record(raw)
    assert rec.venue_market_id == "12345"


def test_to_record_missing_dates_are_none():
    raw = {"id": "1", "conditionId": "0xabc", "question": "Q?", "description": "r"}
    rec = _to_record(raw)
    assert rec.opened_at is None
    assert rec.closes_at is None


def test_to_record_bad_date_is_none_not_crash():
    raw = {"id": "1", "conditionId": "0xabc", "question": "Q?", "description": "r",
           "endDate": "not-a-date"}
    assert _to_record(raw).closes_at is None


# ── _strip_html (ported verbatim from the proven implementation) ─────────────

def test_strip_html_block_elements_to_newlines():
    assert _strip_html("<p>one</p><p>two</p>") == "one\ntwo"


def test_strip_html_list_items_to_bullets():
    out = _strip_html("<ul><li>first</li><li>second</li></ul>")
    assert "- first" in out
    assert "- second" in out


def test_strip_html_entities_decoded():
    assert _strip_html("a &amp; b &gt; c") == "a & b > c"


def test_strip_html_plain_text_passthrough():
    text = 'Resolves "Yes" if X.\n\nOtherwise "No".'
    assert _strip_html(text) == text


def test_strip_html_empty():
    assert _strip_html("") == ""
    assert _strip_html(None) == ""


# ── fetch_markets: pagination with a mocked session ──────────────────────────

class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_fetch_markets_paginates_and_yields_records(gamma_page, monkeypatch):
    # page_limit == fixture size → first page is "full", adapter must fetch again
    pages = [gamma_page, []]  # second page empty → stop
    calls = []

    def fake_get(self, url, params=None, timeout=None):
        calls.append(dict(params))
        return _FakeResponse(pages[len(calls) - 1])

    import requests
    monkeypatch.setattr(requests.Session, "get", fake_get)
    monkeypatch.setattr("ingest.adapters.polymarket.PAGE_DELAY_S", 0)

    records = list(fetch_markets(status="open", page_limit=len(gamma_page)))
    assert len(records) == len(gamma_page)
    assert all(isinstance(r, MarketRecord) for r in records)
    # offset advanced by page size on the second call
    assert calls[0]["offset"] == 0
    assert calls[1]["offset"] == calls[0]["limit"]


def test_fetch_markets_stops_on_short_page(gamma_page, monkeypatch):
    calls = []

    def fake_get(self, url, params=None, timeout=None):
        calls.append(1)
        return _FakeResponse(gamma_page)  # 5 markets < default page_limit 100

    import requests
    monkeypatch.setattr(requests.Session, "get", fake_get)
    monkeypatch.setattr("ingest.adapters.polymarket.PAGE_DELAY_S", 0)

    records = list(fetch_markets(status="open"))
    assert len(records) == len(gamma_page)
    assert len(calls) == 1  # short page means no more data — don't re-fetch


def test_fetch_markets_respects_max_pages(gamma_page, monkeypatch):
    def fake_get(self, url, params=None, timeout=None):
        return _FakeResponse(gamma_page)  # never-ending full pages

    import requests
    monkeypatch.setattr(requests.Session, "get", fake_get)
    monkeypatch.setattr("ingest.adapters.polymarket.PAGE_DELAY_S", 0)

    records = list(fetch_markets(status="open", max_pages=2,
                                 page_limit=len(gamma_page)))
    assert len(records) == 2 * len(gamma_page)


def test_fetch_markets_skips_malformed_market(gamma_page, monkeypatch):
    page = [{"garbage": True}] + gamma_page  # no id/conditionId at all
    pages = [page, []]
    calls = []

    def fake_get(self, url, params=None, timeout=None):
        calls.append(1)
        return _FakeResponse(pages[len(calls) - 1])

    import requests
    monkeypatch.setattr(requests.Session, "get", fake_get)
    monkeypatch.setattr("ingest.adapters.polymarket.PAGE_DELAY_S", 0)

    records = list(fetch_markets(status="open"))
    assert len(records) == len(gamma_page)  # malformed one skipped, not fatal
