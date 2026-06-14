import duckdb
import pandas as pd

from fbball import db, ingest


def _raw_for(season, player_id=201939, game_id="0022400001", date="2024-10-22"):
    """A one-row raw PlayerGameLogs-shaped frame for a given season."""
    return pd.DataFrame(
        [
            {
                "SEASON_YEAR": season, "PLAYER_ID": player_id,
                "PLAYER_NAME": "Test Player", "TEAM_ABBREVIATION": "GSW",
                "GAME_ID": game_id, "GAME_DATE": f"{date}T00:00:00",
                "MIN": 30.0, "FGM": 5, "FGA": 10, "FTM": 2, "FTA": 2,
                "FG3M": 3, "PTS": 15, "REB": 5, "AST": 5,
                "STL": 1, "BLK": 1, "TOV": 2,
            }
        ]
    )


def _recording_fetch(requested):
    """Fake fetcher: records seasons asked for, returns one row per season."""
    def fetch(season, season_type, **kw):
        requested.append(season)
        # unique game_id per season so rows don't collide on the PK
        return _raw_for(season, game_id=f"00224{season[:4]}")
    return fetch


def test_backfill_ingests_all_seasons():
    con = duckdb.connect(":memory:")
    requested = []
    new = ingest.backfill(
        con, ["2022-23", "2023-24", "2024-25"],
        fetch=_recording_fetch(requested), sleep=lambda _: None,
    )
    assert sorted(requested) == ["2022-23", "2023-24", "2024-25"]
    assert new == 3
    assert db.count_game_logs(con) == 3


def test_backfill_skips_seasons_already_marked_complete():
    con = duckdb.connect(":memory:")
    db.init_schema(con)
    db.mark_season_complete(con, "2023-24")

    requested = []
    ingest.backfill(
        con, ["2022-23", "2023-24", "2024-25"], current_season="2099-00",
        fetch=_recording_fetch(requested), sleep=lambda _: None,
    )
    # the completed season is skipped; the other two are pulled
    assert sorted(requested) == ["2022-23", "2024-25"]


def test_backfill_rerun_pulls_nothing_for_historical_seasons():
    con = duckdb.connect(":memory:")
    seasons = ["2023-24", "2024-25"]
    # neither is the current season, so both get marked complete
    ingest.backfill(
        con, seasons, current_season="2099-00",
        fetch=_recording_fetch([]), sleep=lambda _: None,
    )

    requested = []
    new = ingest.backfill(
        con, seasons, current_season="2099-00",
        fetch=_recording_fetch(requested), sleep=lambda _: None,
    )
    assert requested == []
    assert new == 0


def test_backfill_after_loading_newest_first_still_pulls_history():
    """The bug guard: loading the current season first must NOT cause an
    older-season backfill to be skipped."""
    con = duckdb.connect(":memory:")
    # Day 1: only the current season was loaded.
    ingest.backfill(
        con, ["2025-26"], current_season="2025-26",
        fetch=_recording_fetch([]), sleep=lambda _: None,
    )
    # Day 2: backfill the full history including the current season.
    requested = []
    ingest.backfill(
        con, ["2022-23", "2023-24", "2024-25", "2025-26"], current_season="2025-26",
        fetch=_recording_fetch(requested), sleep=lambda _: None,
    )
    # the three historical seasons are pulled; current may re-pull (idempotent)
    assert {"2022-23", "2023-24", "2024-25"} <= set(requested)


def test_backfill_does_not_mark_current_season_complete():
    con = duckdb.connect(":memory:")
    ingest.backfill(
        con, ["2024-25", "2025-26"], current_season="2025-26",
        fetch=_recording_fetch([]), sleep=lambda _: None,
    )
    assert db.is_season_complete(con, "2024-25") is True
    assert db.is_season_complete(con, "2025-26") is False


def test_summary_reports_counts_per_season():
    con = duckdb.connect(":memory:")
    ingest.backfill(
        con, ["2023-24", "2024-25"],
        fetch=_recording_fetch([]), sleep=lambda _: None,
    )
    s = ingest.summary(con)
    assert s["total_rows"] == 2
    assert s["per_season"] == {"2023-24": 1, "2024-25": 1}
    assert s["checkpoint"]["last_season"] == "2024-25"


def test_summary_empty_store():
    con = duckdb.connect(":memory:")
    db.init_schema(con)
    s = ingest.summary(con)
    assert s["total_rows"] == 0
    assert s["per_season"] == {}
    assert s["checkpoint"] is None


def test_update_is_idempotent_on_rerun():
    con = duckdb.connect(":memory:")
    db.init_schema(con)

    def fetch(season, season_type, **kw):
        return _raw_for(season, game_id="0022400999")

    first = ingest.update(con, "2024-25", fetch=fetch)
    second = ingest.update(con, "2024-25", fetch=fetch)
    assert first == 1   # one new game
    assert second == 0  # same game, no duplicate
    assert db.count_game_logs(con) == 1
