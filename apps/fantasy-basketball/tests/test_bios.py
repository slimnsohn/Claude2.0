import duckdb
import pandas as pd

from fbball import db, transform


def _raw_bios():
    """Shape mirrors nba_api LeagueDashPlayerBioStats."""
    return pd.DataFrame([
        {"PLAYER_ID": 201939, "PLAYER_NAME": "Stephen Curry", "AGE": 37.0},
        {"PLAYER_ID": 1630639, "PLAYER_NAME": "A.J. Lawson", "AGE": 25.0},
    ])


def test_normalize_bios_maps_columns():
    out = transform.normalize_bios(_raw_bios(), "2025-26")
    assert list(out.columns) == ["season", "player_id", "age"]
    row = out[out["player_id"] == 201939].iloc[0]
    assert row["season"] == "2025-26"
    assert row["age"] == 37.0


def test_upsert_bios_idempotent():
    con = duckdb.connect(":memory:")
    db.init_schema(con)
    rows = transform.normalize_bios(_raw_bios(), "2025-26")
    db.upsert_bios(con, rows)
    db.upsert_bios(con, rows)
    assert con.execute("SELECT COUNT(*) FROM player_bio").fetchone()[0] == 2


def test_age_for_target_projects_forward():
    """Age in a future target season = latest known age + year offset."""
    con = duckdb.connect(":memory:")
    db.init_schema(con)
    db.upsert_bios(con, transform.normalize_bios(_raw_bios(), "2025-26"))
    ages = db.ages_for_target(con, "2026-27")   # one season ahead
    assert ages[201939] == 38.0   # 37 + 1
    assert ages[1630639] == 26.0
