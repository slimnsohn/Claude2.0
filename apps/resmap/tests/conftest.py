"""Shared fixtures. Integration tests need TEST_DATABASE_URL (see .env.example)
and a loaded schema in that database — they are skipped when it's absent."""
import os

import pytest
from dotenv import load_dotenv

load_dotenv()

TEST_DSN = os.environ.get("TEST_DATABASE_URL")

# Every mutable table, in FK-safe truncation order (CASCADE handles the rest).
ALL_TABLES = ("rule_change_events", "equivalences", "parsed_rules",
              "rule_snapshots", "sources", "markets")


@pytest.fixture
def db_conn():
    """Connection to the resmap_test database with a clean slate per test."""
    if not TEST_DSN:
        pytest.skip("TEST_DATABASE_URL not set")
    psycopg = pytest.importorskip("psycopg")
    conn = psycopg.connect(TEST_DSN)
    with conn.cursor() as cur:
        cur.execute(f"TRUNCATE {', '.join(ALL_TABLES)} CASCADE")
    conn.commit()
    yield conn
    conn.rollback()
    conn.close()
