import sqlite3
from pathlib import Path
import pytest
from odds_pipeline.store import migrate


def test_init_db_creates_all_tables(tmp_path):
    db_path = tmp_path / "test.db"
    migrate.init_db(str(db_path))
    conn = sqlite3.connect(db_path)
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert tables == {
        "segment_types", "bookmakers", "games",
        "odds_snapshots", "scores", "ingest_runs",
    }


def test_init_db_is_idempotent(tmp_path):
    db_path = tmp_path / "test.db"
    migrate.init_db(str(db_path))
    migrate.init_db(str(db_path))  # second call must not error


def test_games_table_has_unique_event_id(tmp_path):
    db_path = tmp_path / "test.db"
    migrate.init_db(str(db_path))
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO games (game_id, sport, commence_time, home_team, away_team, odds_api_event_id) "
        "VALUES ('A', 'NBA', '2025-01-01T00:00Z', 'X', 'Y', 'evt-1')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO games (game_id, sport, commence_time, home_team, away_team, odds_api_event_id) "
            "VALUES ('B', 'NBA', '2025-01-02T00:00Z', 'X', 'Y', 'evt-1')"
        )


def test_odds_snapshots_foreign_keys_enforced_via_helper(tmp_path):
    """The connect() helper must enforce FKs without callers setting the pragma."""
    db_path = tmp_path / "test.db"
    migrate.init_db(str(db_path))
    conn = migrate.connect(str(db_path))  # NOT raw sqlite3.connect
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO odds_snapshots (game_id, bookmaker_key, segment_key, market_type, side, price_american, snapshot_time, raw_archive_path) "
            "VALUES ('nonexistent', 'pinnacle', 'FULL', 'h2h', 'home', -150, '2025-01-01T00:00Z', 'x.json')"
        )


def test_raw_sqlite3_connect_does_not_enforce_fks(tmp_path):
    """Documents the SQLite default — raw sqlite3.connect leaves FKs OFF.
    This is why callers must use migrate.connect()."""
    db_path = tmp_path / "test.db"
    migrate.init_db(str(db_path))
    conn = sqlite3.connect(str(db_path))  # raw — no pragma
    # This insert violates FK but will silently succeed because FKs are OFF.
    conn.execute(
        "INSERT INTO odds_snapshots (game_id, bookmaker_key, segment_key, market_type, side, price_american, snapshot_time, raw_archive_path) "
        "VALUES ('nonexistent', 'pinnacle', 'FULL', 'h2h', 'home', -150, '2025-01-01T00:00Z', 'x.json')"
    )
    rows = conn.execute("SELECT COUNT(*) FROM odds_snapshots").fetchone()[0]
    assert rows == 1  # confirms FKs were OFF
