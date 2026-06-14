import pandas as pd

from fbball import transform
from fbball.db import GAME_LOG_COLUMNS


def _raw_playergamelogs():
    """Shape mirrors nba_api PlayerGameLogs (plural): uppercase cols, ISO dates."""
    return pd.DataFrame(
        [
            {
                "SEASON_YEAR": "2024-25", "PLAYER_ID": 201939,
                "PLAYER_NAME": "Stephen Curry", "TEAM_ABBREVIATION": "GSW",
                "GAME_ID": "0022400001", "GAME_DATE": "2024-10-22T00:00:00",
                "MIN": 34.0, "FGM": 10, "FGA": 20, "FTM": 5, "FTA": 5,
                "FG3M": 6, "PTS": 31, "REB": 5, "AST": 6,
                "STL": 2, "BLK": 0, "TOV": 3,
                "WL": "W", "PLUS_MINUS": 12,  # extra cols that must be dropped
            }
        ]
    )


def test_normalize_produces_exact_schema_columns():
    out = transform.normalize_game_logs(_raw_playergamelogs(), "Regular Season")
    assert list(out.columns) == GAME_LOG_COLUMNS


def test_normalize_maps_values():
    out = transform.normalize_game_logs(_raw_playergamelogs(), "Regular Season")
    row = out.iloc[0]
    assert row["player_id"] == 201939
    assert row["player_name"] == "Stephen Curry"
    assert row["team"] == "GSW"
    assert row["season"] == "2024-25"
    assert row["season_type"] == "Regular Season"
    assert row["game_id"] == "0022400001"
    assert row["tov"] == 3       # TOV -> tov, the 9th cat
    assert row["fg3m"] == 6


def test_normalize_parses_game_date():
    out = transform.normalize_game_logs(_raw_playergamelogs(), "Regular Season")
    assert str(out.iloc[0]["game_date"]) == "2024-10-22"


def test_normalize_empty_frame_returns_empty_with_schema():
    empty = pd.DataFrame(columns=_raw_playergamelogs().columns)
    out = transform.normalize_game_logs(empty, "Regular Season")
    assert list(out.columns) == GAME_LOG_COLUMNS
    assert len(out) == 0
