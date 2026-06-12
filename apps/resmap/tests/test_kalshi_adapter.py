"""Unit tests for the Kalshi adapter — fixture-based, no network, no real creds.

The fixture is a real /trade-api/v2/markets page captured 2026-06-12 (CPI
markets with rules text + multi-leg parlay markets with empty rules). Signing
tests use a throwaway RSA key generated in-test.
"""
import base64
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from ingest.adapters.kalshi import KalshiSession, _to_record, fetch_markets
from ingest.core import MarketRecord

FIXTURE = Path(__file__).parent / "fixtures" / "kalshi_markets_page.json"


@pytest.fixture
def kalshi_page() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture
def rsa_key():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return key, pem


# ── _to_record: field mapping against the real payload ───────────────────────

def test_to_record_maps_real_kalshi_fields(kalshi_page):
    raw = kalshi_page["markets"][0]  # CPI market with rules
    rec = _to_record(raw)
    assert isinstance(rec, MarketRecord)
    assert rec.venue_code == "kalshi"
    assert rec.venue_market_id == raw["ticker"]
    assert rec.title == raw["title"]
    assert rec.status == "open"  # 'active' → 'open'
    assert rec.raw_payload == raw


def test_to_record_rules_text_captured(kalshi_page):
    raw = next(m for m in kalshi_page["markets"] if m.get("rules_primary"))
    rec = _to_record(raw)
    assert raw["rules_primary"] in rec.raw_rules


def test_to_record_concatenates_primary_and_secondary():
    raw = {"ticker": "T", "title": "t", "status": "active",
           "rules_primary": "Primary.", "rules_secondary": "Secondary."}
    rec = _to_record(raw)
    assert rec.raw_rules == "Primary.\nSecondary."


def test_to_record_empty_rules_allowed(kalshi_page):
    # multi-leg parlay markets legitimately have no rules text
    raw = next(m for m in kalshi_page["markets"] if not m.get("rules_primary"))
    rec = _to_record(raw)
    assert rec.raw_rules == ""


def test_to_record_settlement_sources_appended():
    raw = {"ticker": "T", "title": "t", "status": "active",
           "rules_primary": "Rules.",
           "settlement_sources": [{"name": "BLS"}, {"name": "AP"}]}
    rec = _to_record(raw)
    assert "Settlement source: BLS, AP" in rec.raw_rules


def test_to_record_settled_market():
    raw = {"ticker": "T", "title": "t", "status": "settled", "result": "yes",
           "settled_time": "2026-06-01T00:00:00Z"}
    rec = _to_record(raw)
    assert rec.status == "resolved"
    assert rec.outcome == "YES"
    assert rec.resolved_at is not None


def test_to_record_timestamps_tz_aware(kalshi_page):
    rec = _to_record(kalshi_page["markets"][0])
    assert rec.closes_at is not None and rec.closes_at.tzinfo is not None


# ── RSA-PSS signing ──────────────────────────────────────────────────────────

def test_sign_headers_shape_and_verifiability(rsa_key):
    key, pem = rsa_key
    sess = KalshiSession("my-key-id", pem)
    headers = sess.sign_headers("GET", "/trade-api/v2/markets?limit=5")

    assert headers["KALSHI-ACCESS-KEY"] == "my-key-id"
    ts = headers["KALSHI-ACCESS-TIMESTAMP"]
    assert ts.isdigit()

    # signature must verify over "{ts}{METHOD}{path-without-query}"
    payload = f"{ts}GET/trade-api/v2/markets".encode("utf-8")
    key.public_key().verify(
        base64.b64decode(headers["KALSHI-ACCESS-SIGNATURE"]),
        payload,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32),
        hashes.SHA256(),
    )  # raises InvalidSignature on mismatch


def test_unsigned_mode_returns_no_headers():
    sess = KalshiSession()
    assert sess.sign_headers("GET", "/trade-api/v2/markets") == {}


def test_from_env_without_creds_is_unsigned(monkeypatch):
    monkeypatch.delenv("KALSHI_API_KEY_ID", raising=False)
    monkeypatch.delenv("KALSHI_PRIVATE_KEY_PATH", raising=False)
    sess = KalshiSession.from_env()
    assert sess.key_id is None  # public market data still works unsigned


# ── request retry on 429 ─────────────────────────────────────────────────────

class _FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = json.dumps(self._payload)

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"{self.status_code}")

    def json(self):
        return self._payload


def test_request_retries_on_429_then_succeeds(monkeypatch):
    sess = KalshiSession()
    responses = [_FakeResponse(429), _FakeResponse(200, {"ok": True})]
    seen = []

    def fake_request(method, url, headers=None, timeout=None, **kw):
        seen.append(method)
        return responses[len(seen) - 1]

    monkeypatch.setattr(sess.session, "request", fake_request)
    monkeypatch.setattr("ingest.adapters.kalshi.time.sleep", lambda s: None)

    resp = sess.request("GET", "https://x/trade-api/v2/markets")
    assert resp.json() == {"ok": True}
    assert len(seen) == 2


# ── fetch_markets: cursor pagination ─────────────────────────────────────────

def test_fetch_markets_cursor_pagination(kalshi_page, monkeypatch):
    pages = [
        {"cursor": "NEXT", "markets": kalshi_page["markets"]},
        {"cursor": "", "markets": kalshi_page["markets"][:1]},
    ]
    calls = []

    class _FakeSession:
        def request(self, method, url, params=None, **kw):
            calls.append(dict(params or {}))
            return _FakeResponse(200, pages[len(calls) - 1])

    monkeypatch.setattr("ingest.adapters.kalshi.PAGE_DELAY_S", 0)
    records = list(fetch_markets(status="open", session=_FakeSession()))

    assert len(records) == len(kalshi_page["markets"]) + 1
    assert "cursor" not in calls[0]
    assert calls[1]["cursor"] == "NEXT"
    assert calls[0]["market_status"] == "active"


def test_fetch_markets_filters_same_day_parlays_by_default(kalshi_page, monkeypatch):
    """min_close_ts must be sent by default — without it the cursor feed is
    30k+ auto-generated parlay markets with no rules text."""
    calls = []

    class _FakeSession:
        def request(self, method, url, params=None, **kw):
            calls.append(dict(params or {}))
            return _FakeResponse(200, {"cursor": "", "markets": []})

    list(fetch_markets(status="open", session=_FakeSession()))
    assert "min_close_ts" in calls[0]
    assert calls[0]["min_close_ts"] > 0

    calls.clear()
    list(fetch_markets(status="open", session=_FakeSession(),
                       min_close_days=None))
    assert "min_close_ts" not in calls[0]


def test_fetch_markets_max_pages(kalshi_page, monkeypatch):
    class _FakeSession:
        def request(self, method, url, params=None, **kw):
            return _FakeResponse(200, {"cursor": "MORE",
                                       "markets": kalshi_page["markets"]})

    monkeypatch.setattr("ingest.adapters.kalshi.PAGE_DELAY_S", 0)
    records = list(fetch_markets(status="open", max_pages=2,
                                 session=_FakeSession()))
    assert len(records) == 2 * len(kalshi_page["markets"])
