from sports.wnba.residual import compute_residual


def test_residual_zero_when_no_signals():
    res = compute_residual(
        stat="player_points", position="G",
        is_b2b=False, b2b_history=[], teammates_out=[],
        player_stat_avg=20.0,
    )
    assert res.total == 0.0


def test_residual_rest_uses_league_fallback_when_sample_low():
    res = compute_residual(
        stat="player_points", position="G",
        is_b2b=True, b2b_history=[], teammates_out=[],
        player_stat_avg=20.0,
    )
    # G/points b2b factor 0.96 → δ = 20 × 0.96 − 20 = -0.8
    assert abs(res.rest - (-0.8)) < 0.01
    assert res.teammate_out == 0.0


def test_residual_rest_uses_player_history_when_sample_high():
    b2b_history = {
        "b2b":   [{"PTS": v} for v in [16, 18, 14, 19, 15, 17, 16, 15]],
        "rest":  [{"PTS": v} for v in [22, 20, 21, 24, 23, 25, 22, 21]],
    }
    res = compute_residual(
        stat="player_points", position="G",
        is_b2b=True, b2b_history=b2b_history, teammates_out=[],
        player_stat_avg=20.0,
    )
    # 16.25 - 22.25 = -6.0
    assert abs(res.rest - (-6.0)) < 0.01


def test_residual_teammate_out_applies_elasticity():
    res = compute_residual(
        stat="player_points", position="F",
        is_b2b=False, b2b_history=[],
        teammates_out=[{"usage_rate": 0.25}],
        player_stat_avg=18.0,
    )
    # 18 × 0.25 × 0.65 = 2.925
    assert abs(res.teammate_out - 2.925) < 0.001


def test_residual_teammate_out_capped_at_quarter_of_avg():
    res = compute_residual(
        stat="player_points", position="F",
        is_b2b=False, b2b_history=[],
        teammates_out=[{"usage_rate": 0.40}, {"usage_rate": 0.35}],
        player_stat_avg=18.0,
    )
    # cap = 18 × 0.25 = 4.5
    assert abs(res.teammate_out - 4.5) < 0.001
