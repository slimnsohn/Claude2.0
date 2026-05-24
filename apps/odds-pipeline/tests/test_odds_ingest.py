import json
from datetime import datetime, date, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
from odds_pipeline.odds_source import ingest
from odds_pipeline.odds_source.client import Usage

FIXTURES = Path(__file__).parent / "fixtures" / "odds_api"


def test_pull_odds_for_sport_writes_one_archive_per_event(tmp_path):
    events_payload = [
        {"id": "evt-1", "commence_time": "2025-01-16T01:00:00Z",
         "home_team": "Boston Celtics", "away_team": "Los Angeles Lakers"},
        {"id": "evt-2", "commence_time": "2025-01-16T03:30:00Z",
         "home_team": "Miami Heat", "away_team": "New York Knicks"},
    ]
    odds_payload = json.loads((FIXTURES / "historical_event_odds_nba.json").read_text())

    mock_client = MagicMock()
    mock_client.get_historical_events.return_value = (events_payload, Usage(0, 19999, 1))
    mock_client.get_historical_event_odds.return_value = (odds_payload, Usage(0, 19998, 14))

    result = ingest.pull_odds_for_sport(
        client=mock_client,
        sport="NBA",
        date_from=date(2025, 1, 16),
        date_to=date(2025, 1, 16),
        regions=["us", "eu"],
        archive_root=str(tmp_path),
        limit=None,
    )

    assert result.events_processed == 2
    assert result.events_archived == 2
    assert (tmp_path / "NBA" / "2025-01-16").exists()
    archived_files = list((tmp_path / "NBA" / "2025-01-16").glob("*.json"))
    assert len(archived_files) == 2


def test_pull_odds_respects_limit(tmp_path):
    events_payload = [
        {"id": f"evt-{i}", "commence_time": "2025-01-16T01:00:00Z",
         "home_team": "A", "away_team": "B"} for i in range(20)
    ]
    mock_client = MagicMock()
    mock_client.get_historical_events.return_value = (events_payload, Usage(0, 20000, 1))
    mock_client.get_historical_event_odds.return_value = ({}, Usage(0, 19999, 14))

    result = ingest.pull_odds_for_sport(
        client=mock_client, sport="NBA",
        date_from=date(2025, 1, 16), date_to=date(2025, 1, 16),
        regions=["us", "eu"], archive_root=str(tmp_path), limit=5,
    )
    assert result.events_archived == 5


def test_pull_odds_skips_already_archived(tmp_path):
    events_payload = [
        {"id": "evt-1", "commence_time": "2025-01-16T01:00:00Z",
         "home_team": "A", "away_team": "B"},
    ]
    # Pre-create the archive file at the snapshot path the ingest would compute.
    snapshot_dir = tmp_path / "NBA" / "2025-01-16"
    snapshot_dir.mkdir(parents=True)
    # Snapshot time = commence_time - 5min = 2025-01-16T00:55:00Z
    (snapshot_dir / "evt-1__20250116T005500Z.json").write_text("{}")

    mock_client = MagicMock()
    mock_client.get_historical_events.return_value = (events_payload, Usage(0, 20000, 1))
    mock_client.get_historical_event_odds.return_value = ({}, Usage(0, 19999, 14))

    result = ingest.pull_odds_for_sport(
        client=mock_client, sport="NBA",
        date_from=date(2025, 1, 16), date_to=date(2025, 1, 16),
        regions=["us", "eu"], archive_root=str(tmp_path), limit=None,
    )
    # Did NOT call get_historical_event_odds, since archive existed
    assert mock_client.get_historical_event_odds.call_count == 0
    assert result.events_skipped == 1
