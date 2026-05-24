from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock
from odds_pipeline.results_sources import ingest
from odds_pipeline.results_sources.base import GameResult


def test_pull_results_archives_one_file_per_game(tmp_path):
    mock_adapter = MagicMock()
    mock_adapter.sport = "NBA"
    mock_adapter.fetch_completed_games.return_value = [
        GameResult(
            sport="NBA",
            commence_time=datetime(2025, 1, 15, 0, 0, tzinfo=timezone.utc),
            home_team_canonical="LAL", away_team_canonical="BOS",
            source_game_id="0022400500",
            segment_scores={"FULL": (108, 102), "Q1": (24, 28)},
            went_to_ot=False,
            raw_payload={"x": "y"},
        ),
    ]
    res = ingest.pull_results_for_sport(
        adapter=mock_adapter, sport="NBA",
        date_from=date(2025, 1, 15), date_to=date(2025, 1, 15),
        archive_root=str(tmp_path),
    )
    assert res.games_archived == 1
    archived = list((tmp_path / "NBA").glob("*.json"))
    assert len(archived) == 1


def test_pull_results_handles_adapter_exception(tmp_path):
    mock_adapter = MagicMock()
    mock_adapter.sport = "NBA"
    mock_adapter.fetch_completed_games.side_effect = RuntimeError("api down")
    res = ingest.pull_results_for_sport(
        adapter=mock_adapter, sport="NBA",
        date_from=date(2025, 1, 15), date_to=date(2025, 1, 15),
        archive_root=str(tmp_path),
    )
    assert res.games_archived == 0
    assert "api down" in (res.errors[0] if res.errors else "")
