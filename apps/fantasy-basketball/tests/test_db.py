import duckdb
import pandas as pd

from fbball import db


def _sample_rows():
    return pd.DataFrame(
        [
            {
                "player_id": 201939, "player_name": "Stephen Curry", "team": "GSW",
                "season": "2024-25", "season_type": "Regular Season",
                "game_id": "0022400001", "game_date": "2024-10-22",
                "min": 34.0, "fgm": 10, "fga": 20, "ftm": 5, "fta": 5,
                "fg3m": 6, "pts": 31, "reb": 5, "ast": 6, "stl": 2, "blk": 0, "tov": 3,
            },
            {
                "player_id": 2544, "player_name": "LeBron James", "team": "LAL",
                "season": "2024-25", "season_type": "Regular Season",
                "game_id": "0022400001", "game_date": "2024-10-22",
                "min": 35.0, "fgm": 9, "fga": 18, "ftm": 4, "fta": 6,
                "fg3m": 2, "pts": 24, "reb": 8, "ast": 9, "stl": 1, "blk": 1, "tov": 4,
            },
        ]
    )


def test_init_schema_creates_tables():
    con = duckdb.connect(":memory:")
    db.init_schema(con)
    tables = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
    assert {"game_logs", "players", "ingest_state"} <= tables


def test_upsert_inserts_rows():
    con = duckdb.connect(":memory:")
    db.init_schema(con)
    inserted = db.upsert_game_logs(con, _sample_rows())
    assert inserted == 2
    assert db.count_game_logs(con) == 2


def test_upsert_is_idempotent():
    con = duckdb.connect(":memory:")
    db.init_schema(con)
    db.upsert_game_logs(con, _sample_rows())
    inserted_again = db.upsert_game_logs(con, _sample_rows())
    assert inserted_again == 0          # nothing new on the second run
    assert db.count_game_logs(con) == 2  # still no duplicates


def test_checkpoint_absent_returns_none():
    con = duckdb.connect(":memory:")
    db.init_schema(con)
    assert db.get_checkpoint(con, "nba_game_logs") is None


def test_checkpoint_roundtrip():
    con = duckdb.connect(":memory:")
    db.init_schema(con)
    db.set_checkpoint(con, "nba_game_logs", season="2024-25", last_date="2024-12-01")
    cp = db.get_checkpoint(con, "nba_game_logs")
    assert cp["last_season"] == "2024-25"
    assert str(cp["last_date"]) == "2024-12-01"


def test_latest_season_empty_is_none():
    con = duckdb.connect(":memory:")
    db.init_schema(con)
    assert db.latest_season(con) is None


def test_latest_season_returns_max():
    con = duckdb.connect(":memory:")
    db.init_schema(con)
    for season, gid in [("2023-24", "g1"), ("2025-26", "g2"), ("2024-25", "g3")]:
        con.execute(
            "INSERT INTO game_logs (player_id, season, game_id, game_date) "
            "VALUES (1, ?, ?, DATE '2025-11-01')", [season, gid]
        )
    assert db.latest_season(con) == "2025-26"


def test_season_completion_tracking():
    con = duckdb.connect(":memory:")
    db.init_schema(con)
    assert db.is_season_complete(con, "2023-24") is False
    db.mark_season_complete(con, "2023-24")
    assert db.is_season_complete(con, "2023-24") is True


def test_mark_season_complete_is_idempotent():
    con = duckdb.connect(":memory:")
    db.init_schema(con)
    db.mark_season_complete(con, "2023-24")
    db.mark_season_complete(con, "2023-24")
    rows = con.execute("SELECT COUNT(*) FROM completed_seasons").fetchone()[0]
    assert rows == 1


def test_checkpoint_overwrites_same_source():
    con = duckdb.connect(":memory:")
    db.init_schema(con)
    db.set_checkpoint(con, "nba_game_logs", season="2023-24", last_date="2024-04-01")
    db.set_checkpoint(con, "nba_game_logs", season="2024-25", last_date="2024-12-01")
    rows = con.execute("SELECT COUNT(*) FROM ingest_state").fetchone()[0]
    assert rows == 1  # one row per source, updated in place
    assert db.get_checkpoint(con, "nba_game_logs")["last_season"] == "2024-25"
