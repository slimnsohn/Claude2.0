import json
from datetime import date
from pathlib import Path
from unittest.mock import patch
from odds_pipeline.results_sources.mlb import MLBResultsAdapter

FIX = Path(__file__).parent / "fixtures" / "results" / "mlb"


def test_mlb_adapter_per_inning_and_f5():
    sched = json.loads((FIX / "schedule_example.json").read_text())
    linescore_data = json.loads((FIX / "linescore_data_example.json").read_text())
    with patch("odds_pipeline.results_sources.mlb._schedule", return_value=sched), \
         patch("odds_pipeline.results_sources.mlb._linescore_data", return_value=linescore_data):
        adapter = MLBResultsAdapter()
        results = adapter.fetch_completed_games(date(2024, 9, 15), date(2024, 9, 15))
    assert len(results) == 1
    r = results[0]
    assert r.sport == "MLB"
    assert r.home_team_canonical == "Boston Red Sox"
    assert r.away_team_canonical == "New York Yankees"
    assert r.source_game_id == "745671"
    assert r.segment_scores["FULL"] == (6, 4)
    assert r.segment_scores["INN1"] == (1, 0)
    assert r.segment_scores["INN5"] == (2, 0)
    # F5 = sum of innings 1..5
    f5h, f5a = r.segment_scores["F5"]
    inning_sum_h = sum(r.segment_scores[f"INN{i}"][0] for i in range(1, 6))
    inning_sum_a = sum(r.segment_scores[f"INN{i}"][1] for i in range(1, 6))
    assert f5h == inning_sum_h
    assert f5a == inning_sum_a
    assert f5h == 4 and f5a == 3
