from datetime import datetime, date
import pytest
from odds_pipeline.results_sources.base import ResultsAdapter, GameResult


def test_game_result_requires_segment_scores_for_full():
    r = GameResult(
        sport="NBA",
        commence_time=datetime(2025, 1, 15, 19, 30),
        home_team_canonical="LAL", away_team_canonical="BOS",
        source_game_id="0022400500",
        segment_scores={"FULL": (108, 102), "Q1": (24, 28),
                        "Q2": (30, 22), "Q3": (28, 26), "Q4": (26, 26),
                        "H1": (54, 50), "H2": (54, 52)},
        went_to_ot=False,
        raw_payload={"foo": "bar"},
    )
    assert r.segment_scores["FULL"] == (108, 102)


def test_adapter_is_abstract():
    with pytest.raises(TypeError):
        ResultsAdapter()
