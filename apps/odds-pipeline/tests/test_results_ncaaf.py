import json
from datetime import date
from pathlib import Path
from unittest.mock import patch
from odds_pipeline.results_sources.ncaaf import NCAAFResultsAdapter

FIX = Path(__file__).parent / "fixtures" / "results" / "ncaaf"


def test_ncaaf_adapter_per_quarter_scores():
    """Test fetch path: adapter queries year=2024 AND year=2023 (lookback for
    Jan bowl-season games). The mock returns the fixture only for year=2024."""
    payload = json.loads((FIX / "games_2024_week16.json").read_text())

    def fetch_side_effect(year, week=None):
        return payload if year == 2024 else []

    with patch("odds_pipeline.results_sources.ncaaf._fetch_games", side_effect=fetch_side_effect):
        adapter = NCAAFResultsAdapter()
        results = adapter.fetch_completed_games(date(2024, 12, 14), date(2024, 12, 31))
    assert len(results) == 2
    r = results[0]
    assert r.sport == "NCAAF"
    assert r.home_team_canonical == "Ohio State"
    assert r.away_team_canonical == "Tennessee"
    assert r.segment_scores["FULL"] == (42, 17)
    assert r.segment_scores["Q1"] == (14, 3)
    assert r.segment_scores["Q2"] == (7, 7)
    assert r.segment_scores["Q3"] == (14, 0)
    assert r.segment_scores["Q4"] == (7, 7)
    # H1 = Q1+Q2, H2 = Q3+Q4
    assert r.segment_scores["H1"] == (21, 10)
    assert r.segment_scores["H2"] == (21, 7)
    assert r.went_to_ot is False


def test_ncaaf_january_query_uses_prior_year_lookback():
    """Jan 2025 query must fetch year=2024 (where bowl/CFP games live in CFBD)."""
    payload = [
        {
            "id": 999,
            "season": 2024,
            "start_date": "2025-01-20T20:00:00.000Z",
            "completed": True,
            "home_team": "Notre Dame",
            "away_team": "Ohio State",
            "home_points": 23,
            "away_points": 34,
            "home_line_scores": [7, 7, 0, 9],
            "away_line_scores": [7, 14, 6, 7],
        },
    ]
    years_called: list[int] = []

    def fetch_side_effect(year, week=None):
        years_called.append(year)
        return payload if year == 2024 else []

    with patch("odds_pipeline.results_sources.ncaaf._fetch_games", side_effect=fetch_side_effect):
        adapter = NCAAFResultsAdapter()
        results = adapter.fetch_completed_games(date(2025, 1, 1), date(2025, 1, 31))
    assert 2024 in years_called, f"expected 2024 lookback, got {years_called}"
    assert len(results) == 1
    assert results[0].source_game_id == "999"
