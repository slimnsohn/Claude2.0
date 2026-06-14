import duckdb

from fbball import bridge, db, ingest


# ---- normalize_name (pure) ----

def test_normalize_strips_accents():
    assert bridge.normalize_name("Nikola Jokić") == "nikola jokic"
    assert bridge.normalize_name("Luka Dončić") == "luka doncic"


def test_normalize_strips_suffix():
    assert bridge.normalize_name("Jaime Jaquez Jr.") == "jaime jaquez"
    assert bridge.normalize_name("Gary Trent Jr.") == "gary trent"


def test_normalize_strips_punctuation():
    assert bridge.normalize_name("De'Aaron Fox") == "deaaron fox"
    assert bridge.normalize_name("P.J. Washington") == "pj washington"


# ---- matching ----

def _nba(pid, name, active=True, team=None):
    return {"player_id": pid, "full_name": name, "is_active": active, "team": team}


def _ros(key, name, team=""):
    return {"player_key": key, "player_name": name, "editorial_team": team}


def test_match_unique_name():
    nba = [_nba(1, "Jalen Brunson")]
    out = bridge.match_rosters([_ros("p1", "Jalen Brunson")], nba)
    assert out == [{"player_key": "p1", "nba_player_id": 1}]


def test_match_survives_accents_and_suffix():
    nba = [_nba(1, "Nikola Jokić"), _nba(2, "Jaime Jaquez Jr.")]
    out = bridge.match_rosters(
        [_ros("p1", "Nikola Jokic"), _ros("p2", "Jaime Jaquez")], nba
    )
    assert {r["player_key"]: r["nba_player_id"] for r in out} == {"p1": 1, "p2": 2}


def test_collision_resolved_by_active_player():
    # father (retired) + son (active) share a normalized name
    nba = [_nba(10, "Gary Trent", active=False), _nba(11, "Gary Trent Jr.", active=True)]
    out = bridge.match_rosters([_ros("p1", "Gary Trent Jr.")], nba)
    assert out[0]["nba_player_id"] == 11


def test_collision_resolved_by_team_when_both_active():
    nba = [_nba(10, "Marcus Williams", active=True, team="LAL"),
           _nba(11, "Marcus Williams", active=True, team="BKN")]
    out = bridge.match_rosters([_ros("p1", "Marcus Williams", team="BKN")], nba)
    assert out[0]["nba_player_id"] == 11


def test_collision_unresolved_returns_none():
    nba = [_nba(10, "Marcus Williams", active=True, team="LAL"),
           _nba(11, "Marcus Williams", active=True, team="BKN")]
    out = bridge.match_rosters([_ros("p1", "Marcus Williams", team="GSW")], nba)
    assert out[0]["nba_player_id"] is None


def test_alias_handles_nickname():
    nba = [_nba(1, "Nah'Shon Hyland")]
    out = bridge.match_rosters(
        [_ros("p1", "Bones Hyland")], nba,
        aliases={"Bones Hyland": "Nah'Shon Hyland"},
    )
    assert out[0]["nba_player_id"] == 1


def test_no_match_returns_none():
    nba = [_nba(1, "Jalen Brunson")]
    out = bridge.match_rosters([_ros("p1", "Nobody Here")], nba)
    assert out[0]["nba_player_id"] is None


# ---- DB integration ----

def _seed(con):
    db.init_schema(con)
    for pid, name, active, team in [
        (1, "Jalen Brunson", True, "NYK"),
        (10, "Gary Trent", False, None),
        (11, "Gary Trent Jr.", True, "MIL"),
    ]:
        con.execute(
            "INSERT INTO players (player_id, full_name, is_active, team) VALUES (?,?,?,?)",
            [pid, name, active, team],
        )
    for tk, pk, name, et in [
        ("t1", "p1", "Jalen Brunson", "NYK"),
        ("t1", "p2", "Gary Trent Jr.", "MIL"),
        ("t1", "p3", "Unknown Guy", "XXX"),
    ]:
        con.execute(
            "INSERT INTO yahoo_roster (team_key, player_key, player_name, editorial_team) "
            "VALUES (?,?,?,?)",
            [tk, pk, name, et],
        )


def test_bridge_yahoo_players_updates_and_surfaces():
    con = duckdb.connect(":memory:")
    _seed(con)
    result = ingest.bridge_yahoo_players(con)

    assert result["matched"] == 2
    assert result["unmatched"] == ["Unknown Guy"]
    ids = dict(con.execute(
        "SELECT player_key, nba_player_id FROM yahoo_roster ORDER BY player_key"
    ).fetchall())
    assert ids["p1"] == 1
    assert ids["p2"] == 11   # active son, not retired father
    assert ids["p3"] is None


def test_bridge_is_rerunnable():
    con = duckdb.connect(":memory:")
    _seed(con)
    ingest.bridge_yahoo_players(con)
    second = ingest.bridge_yahoo_players(con)   # idempotent
    assert second["matched"] == 2
