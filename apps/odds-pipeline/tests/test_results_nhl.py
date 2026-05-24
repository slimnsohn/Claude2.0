import json
from datetime import date
from pathlib import Path
from unittest.mock import patch
from odds_pipeline.results_sources.nhl import NHLResultsAdapter

FIX = Path(__file__).parent / "fixtures" / "results" / "nhl"


def test_nhl_adapter_returns_per_period_scores():
    schedule = json.loads((FIX / "schedule_20250115.json").read_text())
    box = json.loads((FIX / "boxscore_example.json").read_text())
    with patch("odds_pipeline.results_sources.nhl._fetch_schedule", return_value=schedule), \
         patch("odds_pipeline.results_sources.nhl._fetch_boxscore", return_value=box):
        adapter = NHLResultsAdapter()
        results = adapter.fetch_completed_games(date(2025, 1, 15), date(2025, 1, 15))
    assert len(results) == 1
    r = results[0]
    assert r.sport == "NHL"
    assert r.home_team_canonical == "BOS"
    assert r.away_team_canonical == "NYR"
    assert r.segment_scores["P1"] == (1, 0)
    assert r.segment_scores["P2"] == (2, 1)
    assert r.segment_scores["P3"] == (0, 2)
    assert r.segment_scores["OT1"] == (1, 0)
    assert r.segment_scores["FULL"] == (4, 3)
    assert r.went_to_ot is True
