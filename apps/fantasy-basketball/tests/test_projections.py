import duckdb
import pandas as pd
import pytest

from fbball import db, projections as proj, valuation


def _season(season, gp=70, **rates):
    base = {"season": season, "gp": gp, "mpg": 30,
            "ppg": 0, "rpg": 0, "apg": 0, "spg": 0, "bpg": 0, "topg": 0, "tpm_pg": 0,
            "fgm_pg": 0, "fga_pg": 0, "ftm_pg": 0, "fta_pg": 0}
    base.update(rates)
    return base


def test_single_peak_season_projects_unchanged():
    out = proj.project_player([_season("2025-26", ppg=20)], target_age=26,
                              target_season="2026-27")
    assert out["ppg"] == pytest.approx(20.0, abs=0.3)   # peak age -> ~flat


def test_recency_weights_recent_season_more():
    rows = [_season("2025-26", ppg=30), _season("2024-25", ppg=10)]
    out = proj.project_player(rows, target_age=26, target_season="2026-27")
    # recent (30) weighted ~0.65, prior (10) ~0.35 -> ~23, well above the simple mean of 20
    assert out["ppg"] == pytest.approx(23.0, abs=0.8)


def test_small_sample_season_is_discounted():
    rows = [_season("2025-26", gp=10, ppg=30),   # hot but tiny sample
            _season("2024-25", gp=70, ppg=10)]
    out = proj.project_player(rows, target_age=26, target_season="2026-27")
    assert out["ppg"] < 18.0   # the 10-game 30ppg can't dominate a full prior season


def test_young_player_projects_up_old_projects_down():
    raw = [_season("2025-26", ppg=20)]
    young = proj.project_player(raw, target_age=21, target_season="2026-27")
    old = proj.project_player(raw, target_age=35, target_season="2026-27")
    assert young["ppg"] > 20.0    # rising part of the curve
    assert old["ppg"] < 20.0      # decline


def test_percentages_unaffected_by_age_scaling():
    rows = [_season("2025-26", fgm_pg=5, fga_pg=10, ftm_pg=4, fta_pg=5)]
    out = proj.project_player(rows, target_age=35, target_season="2026-27")
    assert out["fg_pct"] == pytest.approx(0.5)    # 5/10, age cancels in the ratio
    assert out["ft_pct"] == pytest.approx(0.8)


def test_totals_scale_with_projected_gp():
    rows = [_season("2025-26", gp=80, fgm_pg=8, fga_pg=16)]
    out = proj.project_player(rows, target_age=26, target_season="2026-27")
    # fgm_tot ~= projected per-game * projected gp
    assert out["fgm_tot"] == pytest.approx(out["fga_tot"] * 0.5, rel=0.02)
    assert out["fga_tot"] > 1000   # ~16 * ~80


# ---- DB integration: project_players + rank_from_db(source='projection') ----

def _game(pid, gid, season, **stats):
    base = {c: 0 for c in db.GAME_LOG_COLUMNS}
    base.update(player_id=pid, player_name=f"P{pid}", team="GSW", season=season,
                season_type="Regular Season", game_id=gid, game_date="2025-11-01")
    base.update(stats)
    return base


def test_rank_from_db_projection_source():
    con = duckdb.connect(":memory:")
    db.init_schema(con)
    rows = []
    for g in range(5):
        rows.append(_game(1, f"A{g}-25", "2025-26", pts=28, reb=9))
        rows.append(_game(1, f"A{g}-24", "2024-25", pts=24, reb=8))
        rows.append(_game(2, f"B{g}-25", "2025-26", pts=8, reb=2))
        rows.append(_game(2, f"B{g}-24", "2024-25", pts=7, reb=2))
    db.upsert_game_logs(con, pd.DataFrame(rows)[db.GAME_LOG_COLUMNS])
    for pid in (1, 2):
        con.execute("INSERT INTO players (player_id, full_name, is_active) VALUES (?,?,true)",
                    [pid, f"P{pid}"])
    con.execute("INSERT INTO player_bio VALUES ('2025-26', 1, 26.0)")
    con.execute("INSERT INTO player_bio VALUES ('2025-26', 2, 26.0)")

    ranked = valuation.rank_from_db(con, source="projection", min_gp=2, min_min=0)
    assert [r["player_id"] for r in ranked] == [1, 2]   # stud projects higher
    assert ranked[0]["rank"] == 1
