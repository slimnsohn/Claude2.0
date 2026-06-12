"""Tests for the Polymarket API blueprint (trending + ask-the-population).

All network calls are mocked — no real Gamma API traffic.
"""

import json
from unittest.mock import MagicMock

import pytest

from server import create_app


@pytest.fixture
def app(tmp_path):
    app = create_app(data_dir=str(tmp_path))
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


# Gamma-style raw market payloads (arrays JSON-encoded as strings, numbers
# sometimes strings — mirrors the real API's quirks).
FAKE_MARKETS = [
    {
        "question": "Will it rain in New York City on July 4?",
        "id": "111",
        "slug": "nyc-rain-july-4",
        "volume24hr": "50000.5",
        "endDate": "2026-07-04T00:00:00Z",
        "outcomes": '["Yes", "No"]',
        "outcomePrices": '["0.12", "0.88"]',
    },
    {
        "question": "Will Trump's approval rating be above 45%?",
        "id": "222",
        "slug": "trump-approval-45",
        "volume24hr": 250000.0,
        "endDate": "2026-09-30T00:00:00Z",
        "outcomes": '["Yes", "No"]',
        "outcomePrices": '["0.45", "0.55"]',
    },
    # Malformed: no question — must be skipped, not crash the endpoint.
    {"id": "333", "slug": "broken", "volume24hr": "oops"},
]


def _mock_gamma(monkeypatch, payload=FAKE_MARKETS, status=200):
    import api.polymarket as pm
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = payload
    monkeypatch.setattr(pm.requests, "get", lambda *a, **k: resp)


# ---------------------------------------------------------------------------
# /api/polymarket/trending
# ---------------------------------------------------------------------------

def test_trending_success_envelope_sorting_and_coverage(client, tmp_path, monkeypatch):
    _mock_gamma(monkeypatch)
    resp = client.get("/api/polymarket/trending")
    assert resp.status_code == 200
    body = resp.get_json()

    assert body["from_cache"] is False
    assert body["fetched_at"]
    markets = body["markets"]
    assert len(markets) == 2  # malformed third market skipped

    # Sorted by 24h volume desc: Trump market first
    assert markets[0]["market_id"] == "222"
    assert markets[1]["market_id"] == "111"
    assert markets[0]["volume_24h"] == 250000.0
    assert markets[1]["volume_24h"] == 50000.5  # string number parsed

    # CES coverage: Trump approval covered, weather not
    trump = markets[0]
    assert trump["covered"] is True
    assert trump["ces_column"] == "CC24_410"
    assert trump["ces_name"]
    assert trump["ces_topic"] == "approval"
    assert trump["implied_yes"] == 0.45

    rain = markets[1]
    assert rain["covered"] is False
    assert rain["ces_column"] is None
    assert rain["implied_yes"] == 0.12
    assert rain["slug"] == "nyc-rain-july-4"

    # Cache file written
    cache = json.loads((tmp_path / "polymarket_cache.json").read_text())
    assert cache["fetched_at"] == body["fetched_at"]
    assert len(cache["markets"]) == 2


def test_trending_min_score_excludes_single_generic_keyword(client, monkeypatch):
    """Fix 3: a bare generic keyword hit ("trump", score 5) must not be
    marked covered; a multi-keyword hit (trump+approval, score 13) must."""
    payload = [
        {
            "question": "Will Trump restart Project Freedom by June 30?",
            "id": "510", "slug": "project-freedom", "volume24hr": 99000.0,
            "endDate": "2026-06-30T00:00:00Z",
            "outcomes": '["Yes", "No"]', "outcomePrices": '["0.5", "0.5"]',
        },
        {
            "question": "Will Trump's approval rating be above 45%?",
            "id": "511", "slug": "trump-approval", "volume24hr": 88000.0,
            "endDate": "2026-09-30T00:00:00Z",
            "outcomes": '["Yes", "No"]', "outcomePrices": '["0.45", "0.55"]',
        },
    ]
    _mock_gamma(monkeypatch, payload=payload)
    resp = client.get("/api/polymarket/trending")
    assert resp.status_code == 200
    markets = {m["market_id"]: m for m in resp.get_json()["markets"]}

    bare = markets["510"]  # only generic keyword "trump" -> score 5
    assert bare["covered"] is False
    assert bare["ces_column"] is None
    assert bare["match_score"] == 5

    strong = markets["511"]  # trump(5) + approval(8) -> score 13
    assert strong["covered"] is True
    assert strong["ces_column"] == "CC24_410"
    assert strong["match_score"] == 13


def test_trending_filters_sports_and_crypto(client, monkeypatch):
    """Sports futures and crypto markets are excluded from the trending feed —
    they have no public-opinion angle the population can answer."""
    payload = [
        # excluded by category field
        {"question": "Will the Lakers make the playoffs?", "id": "601",
         "slug": "lakers-playoffs", "volume24hr": 900000.0, "category": "Sports",
         "outcomes": '["Yes", "No"]', "outcomePrices": '["0.6", "0.4"]'},
        # excluded by question keyword (no category field)
        {"question": "Will Czechia win the 2026 FIFA World Cup?", "id": "602",
         "slug": "czechia-world-cup", "volume24hr": 800000.0,
         "outcomes": '["Yes", "No"]', "outcomePrices": '["0.01", "0.99"]'},
        {"question": "Will Bitcoin hit $200k by December 31?", "id": "603",
         "slug": "bitcoin-200k", "volume24hr": 700000.0,
         "outcomes": '["Yes", "No"]', "outcomePrices": '["0.12", "0.88"]'},
        # excluded by slug keyword only
        {"question": "Will the price double this year?", "id": "604",
         "slug": "ethereum-price-double", "volume24hr": 600000.0,
         "outcomes": '["Yes", "No"]', "outcomePrices": '["0.2", "0.8"]'},
        # excluded: esports
        {"question": "Counter-Strike: FUT Esports vs G2 (BO3)", "id": "607",
         "slug": "cs-fut-g2", "volume24hr": 500000.0,
         "outcomes": '["Yes", "No"]', "outcomePrices": '["0.5", "0.5"]'},
        # excluded: match-day future with no league keyword
        {"question": "Will Canada win on 2026-06-12?", "id": "608",
         "slug": "canada-2026-06-12", "volume24hr": 400000.0,
         "outcomes": '["Yes", "No"]', "outcomePrices": '["0.7", "0.3"]'},
        # kept: politics
        {"question": "Will Trump's approval rating be above 45%?", "id": "605",
         "slug": "trump-approval", "volume24hr": 100.0,
         "outcomes": '["Yes", "No"]', "outcomePrices": '["0.45", "0.55"]'},
        # kept: "ethics" must NOT trip the \beth\b crypto pattern
        {"question": "Will the House pass new ethics rules?", "id": "606",
         "slug": "house-ethics-rules", "volume24hr": 50.0,
         "outcomes": '["Yes", "No"]', "outcomePrices": '["0.3", "0.7"]'},
        # kept: an election "win" is not a match-day future
        {"question": "Will the GOP win the 2026 midterms?", "id": "609",
         "slug": "gop-midterms", "volume24hr": 25.0,
         "outcomes": '["Yes", "No"]', "outcomePrices": '["0.5", "0.5"]'},
    ]
    _mock_gamma(monkeypatch, payload=payload)
    resp = client.get("/api/polymarket/trending")
    assert resp.status_code == 200
    body = resp.get_json()
    ids = [m["market_id"] for m in body["markets"]]
    assert ids == ["605", "606", "609"]  # volume order, sports/crypto/esports gone
    assert body["excluded_count"] == 6


def test_trending_rows_include_match_score(client, monkeypatch):
    _mock_gamma(monkeypatch)
    resp = client.get("/api/polymarket/trending")
    assert resp.status_code == 200
    for m in resp.get_json()["markets"]:
        assert "match_score" in m


def test_trending_respects_limit(client, monkeypatch):
    _mock_gamma(monkeypatch)
    resp = client.get("/api/polymarket/trending?limit=1")
    assert resp.status_code == 200
    markets = resp.get_json()["markets"]
    assert len(markets) == 1
    assert markets[0]["market_id"] == "222"  # top by volume


def test_trending_network_fail_uses_cache(client, tmp_path, monkeypatch):
    import api.polymarket as pm

    cached = {
        "fetched_at": "2026-06-01T00:00:00+00:00",
        "markets": [{"question": "Cached market?", "market_id": "c1",
                     "slug": "cached", "volume_24h": 1.0, "end_date": None,
                     "implied_yes": None, "covered": False,
                     "ces_column": None, "ces_name": None, "ces_topic": None}],
    }
    (tmp_path / "polymarket_cache.json").write_text(json.dumps(cached))

    def boom(*a, **k):
        raise pm.requests.exceptions.ConnectionError("no network")
    monkeypatch.setattr(pm.requests, "get", boom)

    resp = client.get("/api/polymarket/trending")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["from_cache"] is True
    assert body["fetched_at"] == "2026-06-01T00:00:00+00:00"
    assert body["markets"][0]["question"] == "Cached market?"


def test_trending_network_fail_no_cache_returns_502(client, monkeypatch):
    import api.polymarket as pm

    def boom(*a, **k):
        raise pm.requests.exceptions.ConnectionError("no network")
    monkeypatch.setattr(pm.requests, "get", boom)

    resp = client.get("/api/polymarket/trending")
    assert resp.status_code == 502
    assert "error" in resp.get_json()


def test_trending_http_error_no_cache_returns_502(client, monkeypatch):
    _mock_gamma(monkeypatch, payload=None, status=500)
    resp = client.get("/api/polymarket/trending")
    assert resp.status_code == 502
    assert "500" in resp.get_json()["error"]


# ---------------------------------------------------------------------------
# /api/polymarket/ask
# ---------------------------------------------------------------------------

def test_ask_uncovered_question_400(client):
    resp = client.post("/api/polymarket/ask",
                       json={"question": "Will Bitcoin hit $200k by December 31?"})
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["covered"] is False
    assert "Not covered" in body["error"]


def test_ask_missing_question_400(client):
    resp = client.post("/api/polymarket/ask", json={})
    assert resp.status_code == 400
    assert "question" in resp.get_json()["error"]


def test_ask_covered_question_envelope(client, monkeypatch):
    # Avoid the 180MB CES dependency: stub the synthetic poll itself.
    import api.benchmarks as bm
    calls = []

    def fake_run(question, filters=None):
        calls.append(question)
        return {"yes": 0.52, "no": 0.4, "unsure": 0.08,
                "archetype_count": 12, "profile_count": 5000}
    monkeypatch.setattr(bm, "_run_synthetic", fake_run)

    resp = client.post("/api/polymarket/ask", json={
        "question": "Do you approve of Trump's job performance?", "runs": 3})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["covered"] is True
    assert body["ces_column"] == "CC24_410"
    assert body["ces_name"]
    assert body["runs"] == 3
    assert len(calls) == 3  # averaged over `runs` invocations
    assert body["synthetic"] == {"yes": 0.52, "no": 0.4, "unsure": 0.08}
    assert body["archetype_count"] == 12
    assert body["profile_count"] == 5000


def test_ask_runs_capped_at_25(client, monkeypatch):
    import api.benchmarks as bm
    calls = []
    monkeypatch.setattr(bm, "_run_synthetic", lambda q, filters=None: (
        calls.append(q) or {"yes": 0.5, "no": 0.5, "unsure": 0.0,
                            "archetype_count": 1, "profile_count": 1}))
    resp = client.post("/api/polymarket/ask", json={
        "question": "Do you approve of Trump's job performance?", "runs": 999})
    assert resp.status_code == 200
    assert resp.get_json()["runs"] == 25
    assert len(calls) == 25
