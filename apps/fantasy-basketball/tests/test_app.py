import duckdb
import pandas as pd

from fbball import db
from app import create_app


def _seed_file(path):
    con = duckdb.connect(str(path))
    db.init_schema(con)
    rows = []
    for g in range(3):
        base = {c: 0 for c in db.GAME_LOG_COLUMNS}
        base.update(player_id=1, player_name="Alpha", team="GSW", season="2025-26",
                    season_type="Regular Season", game_id=f"g{g}", game_date="2025-11-01",
                    min=32, pts=25, reb=8, fgm=9, fga=18, ftm=5, fta=6)
        rows.append(base)
    db.upsert_game_logs(con, pd.DataFrame(rows)[db.GAME_LOG_COLUMNS])
    con.execute("INSERT INTO players (player_id, full_name, is_active, nba_position) "
                "VALUES (1,'Alpha',true,'G')")
    con.close()


def _client(tmp_path):
    dbf = tmp_path / "t.duckdb"
    _seed_file(dbf)
    return create_app(str(dbf)).test_client()


def test_overview_endpoint(tmp_path):
    r = _client(tmp_path).get("/api/overview")
    assert r.status_code == 200
    assert r.get_json()["lake"]["game_log_rows"] == 3


def test_players_endpoint(tmp_path):
    r = _client(tmp_path).get("/api/players")
    assert r.status_code == 200
    assert r.get_json()[0]["full_name"] == "Alpha"


def test_rankings_endpoint(tmp_path):
    r = _client(tmp_path).get("/api/rankings?source=season&min_gp=2")
    assert r.status_code == 200
    assert r.get_json()[0]["player_id"] == 1


def test_draft_recommend_endpoint(tmp_path):
    c = _client(tmp_path)
    r = c.post("/api/draft/recommend", json={"drafted_ids": [], "my_ids": [],
                                             "source": "season"})
    assert r.status_code == 200
    assert "available" in r.get_json()
