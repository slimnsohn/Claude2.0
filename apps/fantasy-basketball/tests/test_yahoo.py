import duckdb

from fbball import db, transform, ingest


def _parsed_teams():
    """Shape mirrors yahoo_client.parse_all_rosters() output."""
    return [
        {
            "team_key": "466.l.79957.t.1", "name": "slimpickens",
            "managers": [{"nickname": "Slims"}], "is_my_team": True,
            "players": [
                {"player_key": "466.p.100", "name": "Stephen Curry", "team": "GSW",
                 "position": "PG", "status": "",
                 "eligible_positions": ["PG", "SG", "G", "Util"]},
                {"player_key": "466.p.200", "name": "Nikola Jokic", "team": "DEN",
                 "position": "C", "status": "INJ",
                 "eligible_positions": ["C", "Util"]},
            ],
        },
        {
            "team_key": "466.l.79957.t.2", "name": "Big Baller Brand",
            "managers": [{"nickname": "Jay"}], "is_my_team": False,
            "players": [
                {"player_key": "466.p.300", "name": "LeBron James", "team": "LAL",
                 "position": "SF", "status": "",
                 "eligible_positions": ["SF", "PF", "F", "Util"]},
            ],
        },
    ]


# ---- transform (pure) ----

def test_yahoo_frames_teams():
    teams_df, _ = transform.yahoo_rosters_to_frames(_parsed_teams(), "466.l.79957")
    assert set(teams_df["team_key"]) == {"466.l.79957.t.1", "466.l.79957.t.2"}
    mine = teams_df[teams_df["is_my_team"]]
    assert list(mine["name"]) == ["slimpickens"]


def test_yahoo_frames_roster_joins_eligibility():
    _, roster_df = transform.yahoo_rosters_to_frames(_parsed_teams(), "466.l.79957")
    assert len(roster_df) == 3
    jokic = roster_df[roster_df["player_key"] == "466.p.200"].iloc[0]
    assert jokic["eligible_positions"] == "C,Util"   # list -> comma string
    assert jokic["status"] == "INJ"


# ---- storage ----

def test_upsert_yahoo_teams_idempotent():
    con = duckdb.connect(":memory:")
    db.init_schema(con)
    teams_df, _ = transform.yahoo_rosters_to_frames(_parsed_teams(), "466.l.79957")
    db.upsert_yahoo_teams(con, teams_df)
    db.upsert_yahoo_teams(con, teams_df)
    assert db.count_yahoo_teams(con) == 2


def test_upsert_yahoo_roster_is_a_snapshot():
    """Re-pulling a team replaces its roster (dropped players disappear)."""
    con = duckdb.connect(":memory:")
    db.init_schema(con)
    _, roster_df = transform.yahoo_rosters_to_frames(_parsed_teams(), "466.l.79957")
    db.upsert_yahoo_roster(con, roster_df)
    assert con.execute("SELECT COUNT(*) FROM yahoo_roster").fetchone()[0] == 3

    # team 1 drops Jokic, adds someone else
    changed = [_parsed_teams()[0]]
    changed[0]["players"] = [
        {"player_key": "466.p.100", "name": "Stephen Curry", "team": "GSW",
         "position": "PG", "status": "", "eligible_positions": ["PG"]},
        {"player_key": "466.p.999", "name": "New Guy", "team": "GSW",
         "position": "SG", "status": "", "eligible_positions": ["SG"]},
    ]
    _, changed_df = transform.yahoo_rosters_to_frames(changed, "466.l.79957")
    db.upsert_yahoo_roster(con, changed_df)

    t1_players = {r[0] for r in con.execute(
        "SELECT player_key FROM yahoo_roster WHERE team_key = '466.l.79957.t.1'"
    ).fetchall()}
    assert t1_players == {"466.p.100", "466.p.999"}   # Jokic gone, New Guy in
    # team 2 untouched
    assert con.execute(
        "SELECT COUNT(*) FROM yahoo_roster WHERE team_key = '466.l.79957.t.2'"
    ).fetchone()[0] == 1


# ---- orchestration ----

def test_pull_yahoo_league_stores_via_client():
    con = duckdb.connect(":memory:")

    class FakeClient:
        def get_all_team_rosters(self, league_key):
            return {"_raw": True}

        def parse_all_rosters(self, raw):
            return _parsed_teams()

    result = ingest.pull_yahoo_league(con, "466.l.79957", client=FakeClient())
    assert result["teams"] == 2
    assert result["roster_spots"] == 3
    assert result["my_team"] == "slimpickens"
