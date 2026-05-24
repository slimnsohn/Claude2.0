import sqlite3
from odds_pipeline.store import migrate, seed


def test_seed_bookmakers_inserts_known_books(tmp_path):
    db_path = tmp_path / "test.db"
    migrate.init_db(str(db_path))
    seed.seed_bookmakers(str(db_path))
    conn = sqlite3.connect(db_path)
    keys = {row[0] for row in conn.execute("SELECT key FROM bookmakers")}
    assert {"pinnacle", "draftkings", "fanduel", "betmgm"} <= keys


def test_pinnacle_is_marked_sharp(tmp_path):
    db_path = tmp_path / "test.db"
    migrate.init_db(str(db_path))
    seed.seed_bookmakers(str(db_path))
    conn = sqlite3.connect(db_path)
    sharp = conn.execute(
        "SELECT sharp FROM bookmakers WHERE key='pinnacle'"
    ).fetchone()[0]
    assert sharp == 1


def test_seed_segment_types_covers_all_sports(tmp_path):
    db_path = tmp_path / "test.db"
    migrate.init_db(str(db_path))
    seed.seed_segment_types(str(db_path))
    conn = sqlite3.connect(db_path)
    sports = {row[0] for row in conn.execute("SELECT DISTINCT sport FROM segment_types")}
    assert sports == {"NBA", "NFL", "NHL", "MLB", "NCAAB", "NCAAF"}


def test_nba_segments_include_quarters_halves_overtime(tmp_path):
    db_path = tmp_path / "test.db"
    migrate.init_db(str(db_path))
    seed.seed_segment_types(str(db_path))
    conn = sqlite3.connect(db_path)
    keys = {row[0] for row in conn.execute(
        "SELECT segment_key FROM segment_types WHERE sport='NBA'"
    )}
    assert {"FULL", "Q1", "Q2", "Q3", "Q4", "H1", "H2", "OT1"} <= keys


def test_nhl_uses_periods_and_shootout(tmp_path):
    db_path = tmp_path / "test.db"
    migrate.init_db(str(db_path))
    seed.seed_segment_types(str(db_path))
    conn = sqlite3.connect(db_path)
    keys = {row[0] for row in conn.execute(
        "SELECT segment_key FROM segment_types WHERE sport='NHL'"
    )}
    assert {"FULL", "P1", "P2", "P3", "OT1", "SO"} <= keys


def test_seed_is_idempotent(tmp_path):
    db_path = tmp_path / "test.db"
    migrate.init_db(str(db_path))
    seed.seed_bookmakers(str(db_path))
    seed.seed_bookmakers(str(db_path))  # second call must not duplicate
    conn = sqlite3.connect(db_path)
    pinnacle_count = conn.execute(
        "SELECT COUNT(*) FROM bookmakers WHERE key='pinnacle'"
    ).fetchone()[0]
    assert pinnacle_count == 1
