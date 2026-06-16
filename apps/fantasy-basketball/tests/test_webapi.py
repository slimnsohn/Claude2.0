import duckdb
import pandas as pd

from fbball import db, webapi


def _seed(con):
    db.init_schema(con)
    rows = []
    for season, gid in [("2024-25", "g1"), ("2025-26", "g2")]:
        base = {c: 0 for c in db.GAME_LOG_COLUMNS}
        base.update(player_id=1, player_name="Test Player", team="GSW", season=season,
                    season_type="Regular Season", game_id=gid, game_date="2025-11-01",
                    pts=20)
        rows.append(base)
    db.upsert_game_logs(con, pd.DataFrame(rows)[db.GAME_LOG_COLUMNS])
    con.execute("INSERT INTO players (player_id, full_name, is_active) VALUES (1,'Test Player',true)")
    con.execute("INSERT INTO yahoo_teams VALUES ('t1','lk','slimpickens','me',true)")
    con.execute("INSERT INTO yahoo_roster (team_key, player_key, player_name, nba_player_id) "
                "VALUES ('t1','y1','Test Player',1)")
    return con


def test_overview_reports_lake_summary():
    con = _seed(duckdb.connect(":memory:"))
    out = webapi.overview(con)
    assert out["lake"]["game_log_rows"] == 2
    assert out["lake"]["seasons"] == 2
    assert out["lake"]["season_range"] == ["2024-25", "2025-26"]
    assert out["lake"]["players"] >= 1


def test_overview_includes_my_team():
    con = _seed(duckdb.connect(":memory:"))
    out = webapi.overview(con)
    assert out["my_team"]["name"] == "slimpickens"
    assert out["my_team"]["roster_size"] == 1


def test_overview_handles_empty_store():
    con = duckdb.connect(":memory:")
    db.init_schema(con)
    out = webapi.overview(con)
    assert out["lake"]["game_log_rows"] == 0
    assert out["my_team"] is None   # no yahoo team -> gracefully None


def test_update_state_reports_current_state():
    con = _seed(duckdb.connect(":memory:"))
    con.execute("INSERT INTO ingest_state VALUES ('nba_game_logs','2025-26',DATE '2026-04-12', now())")
    out = webapi.update_state(con)
    assert out["latest_season"] == "2025-26"
    assert out["game_log_rows"] == 2
    assert out["last_updated"] is not None
    # advertises the selectable steps with labels
    keys = [s["key"] for s in out["steps"]]
    assert keys == ["logs", "reference", "ages", "history", "live"]
    assert all(s["label"] for s in out["steps"])


def test_update_state_empty_store_has_no_timestamp():
    con = duckdb.connect(":memory:")
    db.init_schema(con)
    out = webapi.update_state(con)
    assert out["latest_season"] is None
    assert out["last_updated"] is None


def _multi(con):
    """Two players, two seasons each, for table + accordion + rankings."""
    db.init_schema(con)
    rows = []
    specs = [(1, "Alpha", "G", "GSW"), (2, "Beta", "C", "LAL")]
    for pid, name, pos, team in specs:
        con.execute("INSERT INTO players (player_id, full_name, is_active, nba_position, team) "
                    "VALUES (?,?,true,?,?)", [pid, name, pos, team])
        for season, pts in [("2024-25", 10), ("2025-26", 20 if pid == 1 else 8)]:
            for g in range(3):
                base = {c: 0 for c in db.GAME_LOG_COLUMNS}
                base.update(player_id=pid, player_name=name, team=team, season=season,
                            season_type="Regular Season", game_id=f"{pid}{season}{g}",
                            game_date="2025-11-01", pts=pts, reb=5, fgm=4, fga=8)
                rows.append(base)
    db.upsert_game_logs(con, pd.DataFrame(rows)[db.GAME_LOG_COLUMNS])
    return con


def test_players_table_latest_season_with_search():
    con = _multi(duckdb.connect(":memory:"))
    rows = webapi.players(con)
    assert {r["full_name"] for r in rows} == {"Alpha", "Beta"}
    alpha = next(r for r in rows if r["full_name"] == "Alpha")
    assert alpha["season"] == "2025-26"          # latest by default
    assert alpha["ppg"] == 20.0
    # search filters
    only = webapi.players(con, search="alph")
    assert [r["full_name"] for r in only] == ["Alpha"]


def test_players_search_is_accent_insensitive():
    con = duckdb.connect(":memory:")
    db.init_schema(con)
    con.execute("INSERT INTO players (player_id, full_name, is_active) VALUES (1,'Nikola Jokić',true)")
    base = {c: 0 for c in db.GAME_LOG_COLUMNS}
    base.update(player_id=1, player_name="Nikola Jokić", season="2025-26",
                season_type="Regular Season", game_id="g1", game_date="2025-11-01", pts=25)
    db.upsert_game_logs(con, pd.DataFrame([base])[db.GAME_LOG_COLUMNS])
    assert [r["full_name"] for r in webapi.players(con, search="jokic")] == ["Nikola Jokić"]


def test_player_seasons_accordion_all_years_desc():
    con = _multi(duckdb.connect(":memory:"))
    seasons = webapi.player_seasons(con, 1)
    assert [s["season"] for s in seasons] == ["2025-26", "2024-25"]
    assert seasons[0]["ppg"] == 20.0


def test_rankings_returns_valued_players():
    con = _multi(duckdb.connect(":memory:"))
    ranked = webapi.rankings(con, source="season", min_gp=2, min_min=0)
    assert ranked[0]["player_id"] == 1   # Alpha (20 ppg) outranks Beta
    assert "zscores" in ranked[0] and "total_value" in ranked[0]


def test_draft_recommend_weights_my_needs():
    con = _multi(duckdb.connect(":memory:"))
    # I drafted Alpha (a scorer); recommend should value the other available player
    out = webapi.draft_recommend(con, drafted_ids=[1], my_ids=[1],
                                 source="season", min_gp=2, min_min=0)
    avail_ids = [r["player_id"] for r in out["available"]]
    assert 1 not in avail_ids        # drafted is gone
    assert 2 in avail_ids


def _league(con):
    db.init_schema(con)
    # two seasons; same owner wins both under different team names
    for season, tk, name, seed, final in [
        (2024, "t1", "Alphas", 2, 1), (2024, "t2", "Betas", 1, 2),
        (2025, "t3", "Alpha United", 1, 1), (2025, "t4", "Betas", 2, 2),
    ]:
        con.execute("INSERT INTO yh_teams VALUES (?,?,?,?,?,?)",
                    [season, tk, name, "n", "e", "g"])
        con.execute("INSERT INTO yh_standings VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    [season, tk, final, seed, seed, 90, 70, 0, 0.56, "-", "900"])
    for season, tk, oid, label in [
        (2024, "t1", "alphas", "Alphas"), (2024, "t2", "betas", "Betas"),
        (2025, "t3", "alphas", "Alphas"), (2025, "t4", "betas", "Betas"),
    ]:
        con.execute("INSERT INTO yh_owner_identity VALUES (?,?,?,?)",
                    [season, tk, oid, label])
    con.execute("INSERT INTO yh_seasons VALUES (2024,'l24','L',2,NULL,NULL)")
    con.execute("INSERT INTO yh_seasons VALUES (2025,'l25','L',2,NULL,NULL)")
    return con


def test_league_champions_newest_first():
    con = _league(duckdb.connect(":memory:"))
    champs = webapi.league_champions(con)
    assert [c["season"] for c in champs] == [2025, 2024]
    assert champs[0]["owner_label"] == "Alphas"


def test_league_owners_counts_titles():
    con = _league(duckdb.connect(":memory:"))
    owners = {o["owner_label"]: o for o in webapi.league_owners(con)}
    assert owners["Alphas"]["titles"] == 2     # won both seasons
    assert owners["Betas"]["titles"] == 0
    assert owners["Alphas"]["seasons"] == 2
