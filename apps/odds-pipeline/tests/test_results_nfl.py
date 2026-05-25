import json
from datetime import date
from pathlib import Path
from unittest.mock import patch
import pandas as pd
from odds_pipeline.results_sources.nfl import NFLResultsAdapter

FIX = Path(__file__).parent / "fixtures" / "results" / "nfl"


def test_nfl_adapter_returns_full_only():
    """nfl_data_py.import_schedules only exposes full-game scores; per-quarter
    columns do not exist. Adapter must emit ONLY FULL (no synthetic zeros for
    Q1-Q4/H1/H2)."""
    rows = json.loads((FIX / "schedules_2024.json").read_text())
    df = pd.DataFrame(rows)
    with patch("odds_pipeline.results_sources.nfl._import_schedules", return_value=df):
        adapter = NFLResultsAdapter()
        results = adapter.fetch_completed_games(date(2025, 1, 1), date(2025, 1, 31))
    assert len(results) == 2
    r = results[0]
    assert r.sport == "NFL"
    assert r.segment_scores == {"FULL": (27, 32)}
    # Per-quarter/half NOT emitted (missing data shows as missing).
    assert "Q1" not in r.segment_scores
    assert "H1" not in r.segment_scores
    assert r.home_team_canonical == "BUF"
    assert r.away_team_canonical == "KC"
    assert r.went_to_ot is False
