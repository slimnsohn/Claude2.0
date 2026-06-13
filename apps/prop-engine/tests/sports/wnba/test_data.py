import json
from pathlib import Path
import responses

FIXTURE_DIR = Path(__file__).parent.parent.parent / "fixtures"


@responses.activate
def test_fetch_player_game_log_parses_rows():
    from sports.wnba.data import StatsWnbaClient
    fixture = json.loads((FIXTURE_DIR / "stats_wnba_playergamelog.json").read_text())
    responses.add(
        responses.GET,
        "https://stats.wnba.com/stats/playergamelog",
        json=fixture, status=200,
    )
    client = StatsWnbaClient()
    games = client.player_game_log(player_id=1628932, season="2025")
    assert len(games) == 3
    assert games[0]["PTS"] == 26
    assert games[0]["MIN"] == 34
    assert games[1]["REB"] == 8


@responses.activate
def test_stats_wnba_client_sends_required_headers():
    from sports.wnba.data import StatsWnbaClient
    fixture = json.loads((FIXTURE_DIR / "stats_wnba_playergamelog.json").read_text())
    responses.add(
        responses.GET,
        "https://stats.wnba.com/stats/playergamelog",
        json=fixture, status=200,
    )
    client = StatsWnbaClient()
    client.player_game_log(player_id=1628932, season="2025")
    sent = responses.calls[0].request
    assert sent.headers.get("x-nba-stats-origin") == "stats"
    assert sent.headers.get("x-nba-stats-token") == "true"
    assert "wnba.com" in sent.headers.get("Referer", "")
