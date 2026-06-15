import duckdb
import pandas as pd
import pytest

from fbball import db, draft


def _r(pid, value, pos=None):
    return {"player_id": pid, "full_name": f"P{pid}", "nba_position": pos,
            "total_value": value, "zscores": {}}


# ---- tiers (pure) ----

def test_assign_tiers_breaks_on_large_gaps():
    ranked = [_r(1, 10.0), _r(2, 9.8), _r(3, 9.7), _r(4, 5.0), _r(5, 4.9)]
    out = draft.assign_tiers(ranked, gap=1.0)
    assert [r["tier"] for r in out] == [1, 1, 1, 2, 2]


def test_assign_tiers_every_small_gap_one_tier():
    ranked = [_r(1, 5.0), _r(2, 4.9), _r(3, 4.8)]
    out = draft.assign_tiers(ranked, gap=1.0)
    assert {r["tier"] for r in out} == {1}


def test_assign_tiers_handles_empty_and_single():
    assert draft.assign_tiers([], gap=1.0) == []
    assert draft.assign_tiers([_r(1, 3.0)], gap=1.0)[0]["tier"] == 1


# ---- positional ranks (pure) ----

def test_positional_ranks_within_position():
    ranked = [_r(1, 10, "G"), _r(2, 9, "C"), _r(3, 8, "G"), _r(4, 7, "F"), _r(5, 6, "C")]
    out = draft.positional_ranks(ranked)
    pr = {r["player_id"]: r["pos_rank"] for r in out}
    assert pr == {1: "G1", 2: "C1", 3: "G2", 4: "F1", 5: "C2"}


def test_positional_ranks_unknown_position_labeled():
    out = draft.positional_ranks([_r(1, 5, None)])
    assert out[0]["pos_rank"] == "NA1"


def test_positional_ranks_group_by_primary_position():
    # F-C is a forward (primary F); C-F is a center (primary C)
    ranked = [_r(1, 10, "F-C"), _r(2, 9, "C"), _r(3, 8, "C-F")]
    pr = {r["player_id"]: r["pos_rank"] for r in draft.positional_ranks(ranked)}
    assert pr == {1: "F1", 2: "C1", 3: "C2"}


# ---- DB integration ----

def _game(pid, gid, **stats):
    base = {c: 0 for c in db.GAME_LOG_COLUMNS}
    base.update(player_id=pid, player_name=f"P{pid}", team="GSW", season="2025-26",
                season_type="Regular Season", game_id=gid, game_date="2025-11-01")
    base.update(stats)
    return base


def test_build_board_ranks_tiers_and_positions():
    con = duckdb.connect(":memory:")
    db.init_schema(con)
    rows = []
    for g in range(3):
        rows.append(_game(1, f"A{g}", pts=30, reb=10))   # stud
        rows.append(_game(2, f"B{g}", pts=8, reb=3))      # scrub
    db.upsert_game_logs(con, pd.DataFrame(rows)[db.GAME_LOG_COLUMNS])
    con.execute("INSERT INTO players (player_id, full_name, is_active, nba_position) VALUES (1,'P1',true,'G')")
    con.execute("INSERT INTO players (player_id, full_name, is_active, nba_position) VALUES (2,'P2',true,'C')")

    board = draft.build_board(con, season="2025-26", min_gp=2, min_min=0)
    assert [p["player_id"] for p in board] == [1, 2]   # stud first
    assert board[0]["tier"] == 1
    assert board[0]["pos_rank"] == "G1"
    assert board[1]["pos_rank"] == "C1"
