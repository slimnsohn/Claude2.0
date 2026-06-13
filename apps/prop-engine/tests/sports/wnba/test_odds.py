import json
from pathlib import Path
import responses
import pytest

FIXTURE_DIR = Path(__file__).parent.parent.parent / "fixtures"


@pytest.fixture
def events_fixture():
    return json.loads((FIXTURE_DIR / "odds_api_wnba_events.json").read_text())


@pytest.fixture
def event_odds_fixture():
    return json.loads((FIXTURE_DIR / "odds_api_wnba_event_odds.json").read_text())


@responses.activate
def test_fetch_events_returns_normalized(events_fixture):
    from sports.wnba.odds import OddsAPIClient
    responses.add(
        responses.GET,
        "https://api.the-odds-api.com/v4/sports/basketball_wnba/events",
        json=events_fixture,
        status=200,
    )
    client = OddsAPIClient(api_key="TEST")
    events = client.fetch_events()
    assert len(events) == 2
    assert events[0]["event_id"] == "evt-aces-lib-20260519"


@responses.activate
def test_fetch_event_odds_normalizes(event_odds_fixture):
    from sports.wnba.odds import OddsAPIClient
    responses.add(
        responses.GET,
        "https://api.the-odds-api.com/v4/sports/basketball_wnba/events/"
        "evt-aces-lib-20260519/odds",
        json=event_odds_fixture,
        status=200,
    )
    client = OddsAPIClient(api_key="TEST")
    markets = client.fetch_event_player_props("evt-aces-lib-20260519")
    assert len(markets) == 10
    wilson_over = [m for m in markets if m["player_name"] == "A'ja Wilson"
                    and m["side"] == "over"]
    assert len(wilson_over) == 3
    pinnacle_wilson_over = [m for m in wilson_over if m["book"] == "pinnacle"][0]
    assert pinnacle_wilson_over["american_odds"] == -115
    assert pinnacle_wilson_over["line_value"] == 22.5
