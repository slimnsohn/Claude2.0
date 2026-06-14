import duckdb
import pandas as pd

from fbball import db, transform, ingest


def _parsed_fas():
    return [
        {"player_key": "466.p.500", "name": "Free Agent One", "team": "GSW",
         "eligible_positions": ["PG", "G"], "status": ""},
        {"player_key": "466.p.501", "name": "Free Agent Two", "team": "LAL",
         "eligible_positions": ["C"], "status": "INJ"},
    ]


def test_free_agents_to_frame():
    df = transform.free_agents_to_frame(_parsed_fas(), "466.l.79957")
    assert set(df["player_key"]) == {"466.p.500", "466.p.501"}
    one = df[df["player_key"] == "466.p.500"].iloc[0]
    assert one["eligible_positions"] == "PG,G"
    assert one["league_key"] == "466.l.79957"


def test_upsert_free_agents_is_snapshot():
    con = duckdb.connect(":memory:")
    db.init_schema(con)
    df = transform.free_agents_to_frame(_parsed_fas(), "466.l.79957")
    db.upsert_free_agents(con, df)
    assert db.count_free_agents(con) == 2

    # next pull drops FA Two, keeps One -> snapshot reflects it
    smaller = transform.free_agents_to_frame([_parsed_fas()[0]], "466.l.79957")
    db.upsert_free_agents(con, smaller)
    keys = {r[0] for r in con.execute("SELECT player_key FROM yahoo_free_agents").fetchall()}
    assert keys == {"466.p.500"}


def test_pull_free_agents_stores_and_bridges():
    con = duckdb.connect(":memory:")
    db.init_schema(con)
    # seed an NBA player so FA One bridges
    con.execute(
        "INSERT INTO players (player_id, full_name, is_active, team) VALUES (1,'Free Agent One',true,'GSW')"
    )

    class FakeClient:
        def get_free_agents(self, league_key, limit=200):
            return _parsed_fas()

    result = ingest.pull_free_agents(con, "466.l.79957", client=FakeClient())
    assert result["fetched"] == 2
    assert result["matched"] == 1
    assert result["unmatched"] == ["Free Agent Two"]
    pid = con.execute(
        "SELECT nba_player_id FROM yahoo_free_agents WHERE player_key='466.p.500'"
    ).fetchone()[0]
    assert pid == 1
