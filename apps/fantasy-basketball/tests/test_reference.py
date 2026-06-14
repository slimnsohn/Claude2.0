import duckdb
import pandas as pd

from fbball import db, transform, ingest


# ---- static-data fixtures (shape mirrors nba_api.stats.static) ----

def _static_players():
    return [
        {"id": 201939, "full_name": "Stephen Curry", "is_active": True},
        {"id": 76003, "full_name": "Kareem Abdul-Jabbar", "is_active": False},
    ]


def _static_teams():
    return [
        {"id": 1610612744, "full_name": "Golden State Warriors",
         "abbreviation": "GSW", "city": "Golden State", "nickname": "Warriors"},
        {"id": 1610612747, "full_name": "Los Angeles Lakers",
         "abbreviation": "LAL", "city": "Los Angeles", "nickname": "Lakers"},
    ]


def _roster_df():
    """Shape mirrors nba_api CommonTeamRoster: PLAYER_ID + POSITION + team abbr."""
    return pd.DataFrame(
        [{"PLAYER_ID": 201939, "PLAYER": "Stephen Curry", "POSITION": "G",
          "TEAM_ABBREVIATION": "GSW"}]
    )


# ---- transforms (pure) ----

def test_normalize_static_teams():
    out = transform.normalize_teams(_static_teams())
    assert list(out.columns) == ["team_id", "abbreviation", "full_name", "city", "nickname"]
    assert set(out["abbreviation"]) == {"GSW", "LAL"}


def test_normalize_static_players():
    out = transform.normalize_players(_static_players())
    assert list(out.columns) == ["player_id", "full_name", "is_active"]
    curry = out[out["player_id"] == 201939].iloc[0]
    assert curry["full_name"] == "Stephen Curry"
    assert bool(curry["is_active"]) is True


def test_roster_enrichment_maps_position_and_team():
    out = transform.normalize_roster(_roster_df(), team="GSW")
    row = out.iloc[0]
    assert row["player_id"] == 201939
    assert row["nba_position"] == "G"
    assert row["team"] == "GSW"


# ---- storage ----

def test_upsert_teams_idempotent():
    con = duckdb.connect(":memory:")
    db.init_schema(con)
    db.upsert_teams(con, transform.normalize_teams(_static_teams()))
    db.upsert_teams(con, transform.normalize_teams(_static_teams()))
    assert db.count_teams(con) == 2


def test_upsert_players_idempotent():
    con = duckdb.connect(":memory:")
    db.init_schema(con)
    db.upsert_players(con, transform.normalize_players(_static_players()))
    db.upsert_players(con, transform.normalize_players(_static_players()))
    assert db.count_players(con) == 2


def test_enrich_players_sets_position_and_team():
    con = duckdb.connect(":memory:")
    db.init_schema(con)
    db.upsert_players(con, transform.normalize_players(_static_players()))
    db.enrich_players(con, transform.normalize_roster(_roster_df(), team="GSW"))
    row = con.execute(
        "SELECT nba_position, team FROM players WHERE player_id = 201939"
    ).fetchone()
    assert row == ("G", "GSW")


def test_enrich_leaves_unrostered_players_null():
    con = duckdb.connect(":memory:")
    db.init_schema(con)
    db.upsert_players(con, transform.normalize_players(_static_players()))
    db.enrich_players(con, transform.normalize_roster(_roster_df(), team="GSW"))
    # Kareem (retired, not on any roster) keeps NULL position/team
    row = con.execute(
        "SELECT nba_position, team FROM players WHERE player_id = 76003"
    ).fetchone()
    assert row == (None, None)


# ---- orchestration ----

def test_backfill_players_from_game_logs_fills_gap():
    con = duckdb.connect(":memory:")
    db.init_schema(con)
    # static list only knows Curry; a game log exists for an unknown player.
    db.upsert_players(con, transform.normalize_players(
        [{"id": 201939, "full_name": "Stephen Curry", "is_active": True}]
    ))
    con.execute(
        "INSERT INTO game_logs (player_id, player_name, season, game_id, game_date) "
        "VALUES (99999, 'Rookie Newcomer', '2025-26', 'G1', DATE '2026-01-01')"
    )
    added = db.backfill_players_from_game_logs(con, active_season="2025-26")
    assert added == 1
    row = con.execute(
        "SELECT full_name, is_active FROM players WHERE player_id = 99999"
    ).fetchone()
    assert row[0] == "Rookie Newcomer"
    assert row[1] is True  # played in the active season -> active


def test_backfill_players_does_not_overwrite_static_identity():
    con = duckdb.connect(":memory:")
    db.init_schema(con)
    db.upsert_players(con, transform.normalize_players(
        [{"id": 201939, "full_name": "Stephen Curry", "is_active": True}]
    ))
    con.execute(
        "INSERT INTO game_logs (player_id, player_name, season, game_id, game_date) "
        "VALUES (201939, 'S. Curry (logs alias)', '2025-26', 'G1', DATE '2026-01-01')"
    )
    added = db.backfill_players_from_game_logs(con, active_season="2025-26")
    assert added == 0  # already present, untouched
    name = con.execute(
        "SELECT full_name FROM players WHERE player_id = 201939"
    ).fetchone()[0]
    assert name == "Stephen Curry"  # canonical static name preserved


def test_load_reference_populates_both_tables():
    con = duckdb.connect(":memory:")

    def fetch_team_roster(team_abbr):
        # only GSW has our test player
        if team_abbr == "GSW":
            return _roster_df()
        return pd.DataFrame(columns=_roster_df().columns)

    ingest.load_reference(
        con,
        players=_static_players(),
        teams=_static_teams(),
        fetch_team_roster=fetch_team_roster,
        sleep=lambda _: None,
    )
    assert db.count_teams(con) == 2
    assert db.count_players(con) == 2
    pos = con.execute(
        "SELECT nba_position FROM players WHERE player_id = 201939"
    ).fetchone()[0]
    assert pos == "G"
