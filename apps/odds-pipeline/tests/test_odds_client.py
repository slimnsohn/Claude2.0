import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock
from odds_pipeline.odds_source import client

FIXTURES = Path(__file__).parent / "fixtures" / "odds_api"


def _mock_response(status, body, headers=None):
    m = MagicMock()
    m.status_code = status
    m.json.return_value = body
    m.headers = headers or {}
    m.text = json.dumps(body)
    return m


def test_get_historical_events_parses_response():
    fixture = json.loads((FIXTURES / "historical_events_nba_20250115.json").read_text())
    with patch.object(client.requests, "get", return_value=_mock_response(
        200, fixture, {"x-requests-used": "12", "x-requests-remaining": "19988"}
    )):
        c = client.TheOddsApiClient(api_key="x")
        events, usage = c.get_historical_events(
            "basketball_nba",
            datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc),
        )
    assert isinstance(events, list)
    assert usage.requests_used == 12
    assert usage.requests_remaining == 19988


def test_get_historical_event_odds_returns_payload_and_usage():
    fixture = json.loads((FIXTURES / "historical_event_odds_nba.json").read_text())
    with patch.object(client.requests, "get", return_value=_mock_response(
        200, fixture, {"x-requests-used": "26", "x-requests-remaining": "19974"}
    )):
        c = client.TheOddsApiClient(api_key="x")
        payload, usage = c.get_historical_event_odds(
            "basketball_nba",
            "evt-1-syn",
            datetime(2025, 1, 16, 0, 25, tzinfo=timezone.utc),
            regions=["us", "eu"],
            markets=["h2h", "spreads"],
        )
    assert payload == fixture
    assert usage.requests_used == 26


def test_client_retries_on_429(monkeypatch):
    monkeypatch.setattr(client, "BACKOFF_SECONDS", [0, 0, 0])
    rate_limited = _mock_response(429, {}, {})
    success = _mock_response(200, {"data": [], "timestamp": "2025-01-15T12:00:00Z"}, {"x-requests-used": "1"})
    with patch.object(client.requests, "get", side_effect=[rate_limited, success]):
        c = client.TheOddsApiClient(api_key="x")
        events, usage = c.get_historical_events(
            "basketball_nba",
            datetime(2025, 1, 15, tzinfo=timezone.utc),
        )
    assert events == []


def test_client_raises_after_exhausting_429_retries(monkeypatch):
    import pytest
    monkeypatch.setattr(client, "BACKOFF_SECONDS", [0, 0, 0])
    rate_limited = _mock_response(429, {}, {})
    with patch.object(client.requests, "get", return_value=rate_limited):
        c = client.TheOddsApiClient(api_key="x")
        with pytest.raises(RuntimeError, match="429"):
            c.get_historical_events(
                "basketball_nba",
                datetime(2025, 1, 15, tzinfo=timezone.utc),
            )
