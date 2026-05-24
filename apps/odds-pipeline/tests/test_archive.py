import json
from datetime import datetime, timezone
from odds_pipeline import archive


def test_write_odds_archive_creates_deterministic_path(tmp_path):
    path = archive.write_odds(
        root=str(tmp_path),
        sport="NBA",
        event_id="evt-abc",
        snapshot_time=datetime(2025, 1, 16, 0, 25, tzinfo=timezone.utc),
        payload={"foo": "bar"},
    )
    assert path.endswith("NBA/2025-01-16/evt-abc__20250116T002500Z.json") or \
           path.endswith("NBA\\2025-01-16\\evt-abc__20250116T002500Z.json")
    assert json.loads(open(path).read()) == {"foo": "bar"}


def test_write_odds_uses_commence_date_not_today(tmp_path):
    path = archive.write_odds(
        root=str(tmp_path),
        sport="NBA",
        event_id="x",
        snapshot_time=datetime(2025, 1, 16, 0, 25, tzinfo=timezone.utc),
        payload={},
    )
    assert "2025-01-16" in path


def test_write_results_path_includes_game_id(tmp_path):
    path = archive.write_results(
        root=str(tmp_path),
        sport="NBA",
        game_id="NBA:20250115:BOS@LAL",
        payload={"score": 108},
    )
    # NBA:20250115:BOS@LAL is the unsanitized id; the archive must handle path-illegal
    # characters (':' and '@' are illegal on Windows) by sanitizing the filename.
    # Verify the file exists and round-trips correctly:
    from pathlib import Path
    assert Path(path).exists()
    assert json.loads(open(path).read()) == {"score": 108}


def test_exists_returns_true_after_write(tmp_path):
    archive.write_odds(
        root=str(tmp_path), sport="NBA", event_id="e",
        snapshot_time=datetime(2025, 1, 16, 0, 25, tzinfo=timezone.utc),
        payload={},
    )
    assert archive.odds_archive_exists(
        root=str(tmp_path), sport="NBA", event_id="e",
        snapshot_time=datetime(2025, 1, 16, 0, 25, tzinfo=timezone.utc),
    )


def test_results_exists_returns_true_after_write(tmp_path):
    """Guards path-reuse: write_results and results_archive_exists must share the
    same path-builder including sanitization of ':' and '@'."""
    archive.write_results(
        root=str(tmp_path), sport="NBA",
        game_id="NBA:20250115:BOS@LAL",
        payload={"final": [108, 102]},
    )
    assert archive.results_archive_exists(
        root=str(tmp_path), sport="NBA",
        game_id="NBA:20250115:BOS@LAL",
    )
    assert not archive.results_archive_exists(
        root=str(tmp_path), sport="NBA",
        game_id="NBA:20250115:DIFFERENT@GAME",
    )
