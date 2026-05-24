import json
from datetime import date
from pathlib import Path
from unittest.mock import patch
from odds_pipeline.results_sources.ncaab import NCAABResultsAdapter

FIX = Path(__file__).parent / "fixtures" / "results" / "ncaab"


def test_ncaab_adapter_per_half_scores():
    payload = json.loads((FIX / "scoreboard_example.json").read_text())
    with patch("odds_pipeline.results_sources.ncaab._fetch_scoreboard", return_value=payload):
        adapter = NCAABResultsAdapter()
        results = adapter.fetch_completed_games(date(2025, 1, 15), date(2025, 1, 15))
    assert len(results) == 2

    # Game 1: DUKE 78, UNC 70, no OT
    game1 = results[0]
    assert game1.sport == "NCAAB"
    assert game1.home_team_canonical == "DUKE"
    assert game1.away_team_canonical == "UNC"
    assert game1.segment_scores["H1"] == (42, 33)
    assert game1.segment_scores["H2"] == (36, 37)
    assert game1.segment_scores["FULL"] == (78, 70)
    assert game1.went_to_ot is False

    # Game 2: KU 85, KSU 82, with OT1
    game2 = results[1]
    assert game2.segment_scores["H1"] == (35, 30)
    assert game2.segment_scores["H2"] == (38, 43)
    assert game2.segment_scores["OT1"] == (12, 9)
    assert game2.segment_scores["FULL"] == (85, 82)
    assert game2.went_to_ot is True
