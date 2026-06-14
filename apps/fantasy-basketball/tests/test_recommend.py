import duckdb
import pandas as pd
import pytest

from fbball import db, recommend


def _p(pid, **z):
    """A valued player: zscores for the named cats, 0 elsewhere."""
    return {"player_id": pid, "full_name": f"P{pid}", "zscores": dict(z)}


def test_category_profile_sums_zscores_across_roster():
    roster = [_p(1, PTS=2.0, REB=1.0), _p(2, PTS=1.0, REB=-0.5)]
    prof = recommend.category_profile(roster)
    assert prof["PTS"] == pytest.approx(3.0)
    assert prof["REB"] == pytest.approx(0.5)
    assert prof["AST"] == 0.0   # absent cat -> 0


def test_needs_weights_weakest_cat_gets_highest_weight():
    profile = {c: 0.0 for c in recommend.CATS}
    profile["PTS"] = 5.0    # strong
    profile["REB"] = -3.0   # weak
    profile["AST"] = 1.0    # middle
    w = recommend.needs_weights(profile)
    assert w["REB"] == pytest.approx(1.0)   # weakest -> full weight
    assert w["PTS"] == pytest.approx(0.0)   # strongest -> no weight
    assert 0.0 < w["AST"] < 1.0


def test_needs_weights_zeroes_punted_cats():
    profile = {c: 0.0 for c in recommend.CATS}
    profile["PTS"] = 5.0
    profile["REB"] = -3.0
    w = recommend.needs_weights(profile, punt={"REB"})
    assert w["REB"] == 0.0   # punted -> ignored even though it's weakest


def test_score_for_needs_is_weighted_sum():
    weights = {c: 0.0 for c in recommend.CATS}
    weights["REB"] = 1.0
    weights["AST"] = 0.5
    fa = _p(9, REB=2.0, AST=4.0, PTS=10.0)
    assert recommend.score_for_needs(fa, weights) == pytest.approx(2.0 * 1 + 4.0 * 0.5)


def test_rank_waivers_prefers_fit_over_raw_value():
    """A FA who fills my weak cat beats one who piles onto my strong cat,
    even at equal raw totals."""
    profile = {c: 0.0 for c in recommend.CATS}
    profile["PTS"] = 5.0     # I'm strong in PTS
    profile["REB"] = -4.0    # I'm weak in REB
    weights = recommend.needs_weights(profile)

    fills_need = _p(1, REB=3.0)   # helps my weak cat
    piles_on = _p(2, PTS=3.0)     # piles onto my strong cat (weight ~0)
    ranked = recommend.rank_waivers([piles_on, fills_need], weights)

    assert ranked[0]["player_id"] == 1
    assert ranked[0]["rank"] == 1
    assert ranked[0]["needs_value"] > ranked[1]["needs_value"]


def test_rank_waivers_handles_flat_profile():
    """No spread in my categories -> every cat equally needed, no crash."""
    profile = {c: 0.0 for c in recommend.CATS}
    weights = recommend.needs_weights(profile)
    ranked = recommend.rank_waivers([_p(1, PTS=2.0), _p(2, REB=1.0)], weights)
    assert [r["player_id"] for r in ranked] == [1, 2]   # higher total wins


# ---- DB integration: end-to-end waiver recommendation ----

def _game(pid, gid, **stats):
    base = {c: 0 for c in db.GAME_LOG_COLUMNS}
    base.update(player_id=pid, player_name=f"P{pid}", team="GSW", season="2025-26",
                season_type="Regular Season", game_id=gid, game_date="2025-11-01")
    base.update(stats)
    return base


def test_recommend_waivers_prefers_filling_my_weak_cat():
    con = duckdb.connect(":memory:")
    db.init_schema(con)
    # Pool of 3 players: my roster has a PTS monster (weak REB);
    # FA A is a rebounder, FA B is a scorer.
    rows = []
    for g in range(3):
        rows.append(_game(3, f"C{g}", pts=30, reb=2))   # my player C
        rows.append(_game(1, f"A{g}", pts=5, reb=14))   # FA A (rebounds)
        rows.append(_game(2, f"B{g}", pts=25, reb=2))   # FA B (scores)
    db.upsert_game_logs(con, pd.DataFrame(rows)[db.GAME_LOG_COLUMNS])
    for pid in (1, 2, 3):
        con.execute("INSERT INTO players (player_id, full_name, is_active) VALUES (?,?,true)",
                    [pid, f"P{pid}"])

    con.execute("INSERT INTO yahoo_teams VALUES ('t1','lk','Mine','me',true)")
    con.execute("INSERT INTO yahoo_roster (team_key, player_key, player_name, nba_player_id) "
                "VALUES ('t1','y3','P3',3)")
    for pk, pid, name in [("y1", 1, "P1"), ("y2", 2, "P2")]:
        con.execute(
            "INSERT INTO yahoo_free_agents (league_key, player_key, player_name, nba_player_id) "
            "VALUES ('lk',?,?,?)", [pk, name, pid])

    out = recommend.recommend_waivers(con, season="2025-26", min_gp=2, min_min=0)
    assert out["pool"] == 2
    # I'm weak in REB -> the rebounder (player 1) should top the list
    assert out["recommendations"][0]["player_id"] == 1
