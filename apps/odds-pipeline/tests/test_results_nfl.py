import json
from datetime import date
from pathlib import Path
from unittest.mock import patch
import pandas as pd
from odds_pipeline.results_sources.nfl import NFLResultsAdapter

FIX = Path(__file__).parent / "fixtures" / "results" / "nfl"


def test_nfl_adapter_returns_per_quarter_scores():
    rows = json.loads((FIX / "schedules_2024.json").read_text())
    df = pd.DataFrame(rows)
    with patch("odds_pipeline.results_sources.nfl._import_schedules", return_value=df):
        adapter = NFLResultsAdapter()
        results = adapter.fetch_completed_games(date(2025, 1, 1), date(2025, 1, 31))
    assert len(results) == 2
    r = results[0]
    assert r.sport == "NFL"
    assert "FULL" in r.segment_scores
    assert "Q1" in r.segment_scores
    h1h, h1a = r.segment_scores["H1"]
    q1h, q1a = r.segment_scores["Q1"]
    q2h, q2a = r.segment_scores["Q2"]
    assert h1h == q1h + q2h
    assert h1a == q1a + q2a
    # Verify a specific game's FULL — KC at BUF in fixture row 0: home=BUF (27), away=KC (32)
    assert r.home_team_canonical == "BUF"
    assert r.away_team_canonical == "KC"
    assert r.segment_scores["FULL"] == (27, 32)
    assert r.went_to_ot is False
