"""Database schema migration and connection helper."""
import sqlite3
from pathlib import Path


SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def connect(db_path: str) -> sqlite3.Connection:
    """Open a SQLite connection with foreign keys enforced.

    SQLite's PRAGMA foreign_keys is a per-connection runtime flag; setting it
    in schema.sql only affects the init_db connection. Every caller that opens
    a new connection must enable FKs explicitly. Use this helper everywhere
    instead of raw sqlite3.connect().
    """
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: str) -> None:
    """Create database from schema.sql. Idempotent."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA_PATH.read_text())
        conn.commit()
    finally:
        conn.close()
