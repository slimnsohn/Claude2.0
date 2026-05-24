import json
from datetime import date
from pathlib import Path
from unittest.mock import patch
from odds_pipeline.results_sources.ncaaf import NCAAFResultsAdapter

FIX = Path(__file__).parent / "fixtures" / "results" / "ncaaf"


def test_ncaaf_adapter_per_quarter_scores():
    payload = json.loads((FIX / "games_2024_week16.json").read_text())
    with patch("odds_pipeline.results_sources.ncaaf._fetch_games", return_value=payload):
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
