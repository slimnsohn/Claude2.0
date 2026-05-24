import json
from datetime import date
from pathlib import Path
from unittest.mock import patch, MagicMock
from odds_pipeline.results_sources.nba import NBAResultsAdapter

FIX = Path(__file__).parent / "fixtures" / "results" / "nba"


def test_nba_adapter_returns_per_quarter_scores():
    boxscore_payload = json.loads((FIX / "boxscore_0022400500.json").read_text())
    games_list = [
        {"GAME_ID": "0022400500", "GAME_DATE": "2025-01-15",
         "TEAM_ABBREVIATION": "LAL", "MATCHUP": "LAL vs. BOS",
         "WL": "W", "MIN": 240},
        {"GAME_ID": "0022400500", "GAME_DATE": "2025-01-15",
         "TEAM_ABBREVIATION": "BOS", "MATCHUP": "BOS @ LAL",
         "WL": "L", "MIN": 240},
    ]
    with patch("odds_pipeline.results_sources.nba._list_games", return_value=games_list), \
         patch("odds_pipeline.results_sources.nba._fetch_boxscore", return_value=boxscore_payload):
        adapter = NBAResultsAdapter()
        results = adapter.fetch_completed_games(date(2025, 1, 15), date(2025, 1, 15))

    assert len(results) == 1
    r = results[0]
    assert r.sport == "NBA"
    assert r.source_game_id == "0022400500"
    assert r.home_team_canonical == "LAL"
    assert r.away_team_canonical == "BOS"
    assert r.went_to_ot is False
    assert r.segment_scores["FULL"] == (108, 102)
    # H1 = Q1+Q2, H2 = Q3+Q4
    q1h, q1a = r.segment_scores["Q1"]
    q2h, q2a = r.segment_scores["Q2"]
    h1h, h1a = r.segment_scores["H1"]
    assert h1h == q1h + q2h
    assert h1a == q1a + q2a
