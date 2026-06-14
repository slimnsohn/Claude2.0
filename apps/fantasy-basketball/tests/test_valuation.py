import duckdb
import pandas as pd
import pytest

from fbball import db, valuation


def _player(pid, **over):
    """A valuation input row; all stats default to 0, override per-cat."""
    base = {
        "player_id": pid, "full_name": f"P{pid}", "gp": 70, "mpg": 30,
        "ppg": 0, "rpg": 0, "apg": 0, "spg": 0, "bpg": 0, "topg": 0, "tpm_pg": 0,
        "fg_pct": 0, "ft_pct": 0, "fga_pg": 0, "fta_pg": 0,
        "fgm_tot": 0, "fga_tot": 0, "ftm_tot": 0, "fta_tot": 0,
    }
    base.update(over)
    return base


def _by_id(results):
    return {r["player_id"]: r for r in results}


def test_higher_counting_stat_ranks_higher():
    out = valuation.compute_values([_player(1, ppg=30), _player(2, ppg=10)])
    assert out[0]["player_id"] == 1          # sorted by total value desc
    assert out[0]["rank"] == 1 and out[1]["rank"] == 2
    assert out[0]["zscores"]["PTS"] > 0 > out[1]["zscores"]["PTS"]


def test_turnovers_are_inverted():
    """Fewer turnovers is better — the TOV z-score rewards the low-TO player."""
    res = _by_id(valuation.compute_values([_player(1, topg=1), _player(2, topg=5)]))
    assert res[1]["zscores"]["TOV"] > 0     # 1 TO/game -> positive
    assert res[2]["zscores"]["TOV"] < 0     # 5 TO/game -> negative


def test_percentage_cats_are_volume_weighted_impact():
    """Two 90% FT shooters: the higher-VOLUME one is worth more. This is the
    impact method — raw percentage alone would tie them."""
    players = [
        _player(1, ft_pct=0.90, fta_pg=2, ftm_tot=180, fta_tot=200),  # low volume
        _player(2, ft_pct=0.90, fta_pg=8, ftm_tot=720, fta_tot=800),  # high volume
        _player(3, ft_pct=0.70, fta_pg=5, ftm_tot=350, fta_tot=500),  # drags league avg down
    ]
    res = _by_id(valuation.compute_values(players))
    assert players[0]["ft_pct"] == players[1]["ft_pct"]          # same percentage
    assert res[2]["zscores"]["FT_PCT"] > res[1]["zscores"]["FT_PCT"]  # volume wins
    assert res[3]["zscores"]["FT_PCT"] < 0                        # below-avg shooter


def test_punt_excludes_category_from_total():
    players = [_player(1, ppg=30, topg=4), _player(2, ppg=10, topg=1)]
    full = _by_id(valuation.compute_values(players))
    punted = _by_id(valuation.compute_values(players, punt={"PTS"}))
    for pid in (1, 2):
        expected = full[pid]["total_value"] - full[pid]["zscores"]["PTS"]
        assert punted[pid]["total_value"] == pytest.approx(expected)


def test_zero_variance_category_is_safe():
    """All players identical in a cat -> z=0, no division by zero."""
    out = valuation.compute_values([_player(1, ppg=15), _player(2, ppg=15)])
    for r in out:
        assert r["zscores"]["PTS"] == 0.0


def test_total_value_sums_unpunted_zscores():
    out = valuation.compute_values([_player(1, ppg=30, rpg=10), _player(2, ppg=10, rpg=2)])
    r = _by_id(out)[1]
    assert r["total_value"] == pytest.approx(sum(r["zscores"].values()))


# ---- DB integration ----

def _game(player_id, game_id, **stats):
    base = {c: 0 for c in db.GAME_LOG_COLUMNS}
    base.update(player_id=player_id, player_name=f"P{player_id}", team="GSW",
                season="2025-26", season_type="Regular Season",
                game_id=game_id, game_date="2025-11-01")
    base.update(stats)
    return base


def test_rank_from_db_orders_by_value():
    con = duckdb.connect(":memory:")
    db.init_schema(con)
    rows = []
    for g in range(5):
        rows.append(_game(1, f"A{g}", pts=30, reb=10, ast=8))   # star
        rows.append(_game(2, f"B{g}", pts=6, reb=2, ast=1))     # scrub
    db.upsert_game_logs(con, pd.DataFrame(rows)[db.GAME_LOG_COLUMNS])

    ranked = valuation.rank_from_db(con, season="2025-26", min_gp=2, min_min=0)
    assert [r["player_id"] for r in ranked] == [1, 2]
    assert ranked[0]["rank"] == 1


def test_rank_from_db_respects_gp_filter():
    con = duckdb.connect(":memory:")
    db.init_schema(con)
    rows = [_game(1, "A0", pts=30)]                    # only 1 game
    rows += [_game(2, f"B{g}", pts=10) for g in range(5)]
    db.upsert_game_logs(con, pd.DataFrame(rows)[db.GAME_LOG_COLUMNS])

    ranked = valuation.rank_from_db(con, season="2025-26", min_gp=3, min_min=0)
    assert [r["player_id"] for r in ranked] == [2]   # player 1 filtered out
