import duckdb
import pandas as pd
import pytest

from fbball import db

COLS = db.GAME_LOG_COLUMNS


def _game(player_id, game_id, date, season="2025-26", **stats):
    """A game_logs row with everything defaulted to 0, overridable by kwarg."""
    base = {c: 0 for c in COLS}
    base.update(
        player_id=player_id, player_name=f"P{player_id}", team="GSW",
        season=season, season_type="Regular Season",
        game_id=game_id, game_date=date,
    )
    base.update(stats)
    return base


def _insert(con, rows):
    db.upsert_game_logs(con, pd.DataFrame(rows)[COLS])


def test_season_stats_games_played_and_ppg():
    con = duckdb.connect(":memory:")
    db.init_schema(con)
    _insert(con, [
        _game(1, "G1", "2025-10-22", pts=4),
        _game(1, "G2", "2025-10-24", pts=6),
    ])
    row = con.execute(
        "SELECT gp, ppg FROM player_season_stats WHERE player_id = 1"
    ).fetchone()
    assert row[0] == 2          # games played
    assert row[1] == pytest.approx(5.0)   # (4+6)/2


def test_season_stats_percentages_are_volume_weighted():
    """The classic z-score trap: FG% must be total makes / total attempts,
    NOT the average of per-game percentages."""
    con = duckdb.connect(":memory:")
    db.init_schema(con)
    _insert(con, [
        _game(1, "G1", "2025-10-22", fgm=1, fga=1, ftm=2, fta=2),   # 100% FG
        _game(1, "G2", "2025-10-24", fgm=3, fga=9, ftm=0, fta=4),   # 33% FG
    ])
    fg_pct, ft_pct = con.execute(
        "SELECT fg_pct, ft_pct FROM player_season_stats WHERE player_id = 1"
    ).fetchone()
    assert fg_pct == pytest.approx(4 / 10)   # not (1.0 + 0.333)/2
    assert ft_pct == pytest.approx(2 / 6)


def test_season_stats_zero_attempts_gives_null_pct():
    con = duckdb.connect(":memory:")
    db.init_schema(con)
    _insert(con, [_game(1, "G1", "2025-10-22", fgm=0, fga=0)])
    fg_pct = con.execute(
        "SELECT fg_pct FROM player_season_stats WHERE player_id = 1"
    ).fetchone()[0]
    assert fg_pct is None   # 0 attempts -> undefined, not a div-by-zero


def test_season_stats_splits_by_season():
    con = duckdb.connect(":memory:")
    db.init_schema(con)
    _insert(con, [
        _game(1, "G1", "2024-10-22", season="2024-25", pts=10),
        _game(1, "G2", "2025-10-22", season="2025-26", pts=20),
    ])
    rows = con.execute(
        "SELECT season, ppg FROM player_season_stats WHERE player_id = 1 ORDER BY season"
    ).fetchall()
    assert rows == [("2024-25", 10.0), ("2025-26", 20.0)]


def test_recent_form_caps_at_15_most_recent_games():
    con = duckdb.connect(":memory:")
    db.init_schema(con)
    rows = []
    # 5 old games (pts=0) then 15 recent games (pts=10)
    for i in range(5):
        rows.append(_game(1, f"OLD{i}", f"2025-11-{i+1:02d}", pts=0))
    for i in range(15):
        rows.append(_game(1, f"NEW{i}", f"2025-12-{i+1:02d}", pts=10))
    _insert(con, rows)
    gp_window, ppg = con.execute(
        "SELECT gp_window, ppg FROM player_recent_form WHERE player_id = 1"
    ).fetchone()
    assert gp_window == 15            # capped at 15
    assert ppg == pytest.approx(10.0)  # only the recent games count


def test_recent_form_uses_current_season_only():
    con = duckdb.connect(":memory:")
    db.init_schema(con)
    _insert(con, [
        _game(1, "OLD", "2024-12-01", season="2024-25", pts=99),
        _game(1, "NEW", "2025-12-01", season="2025-26", pts=10),
    ])
    ppg = con.execute(
        "SELECT ppg FROM player_recent_form WHERE player_id = 1"
    ).fetchone()[0]
    assert ppg == pytest.approx(10.0)  # last season's game excluded
