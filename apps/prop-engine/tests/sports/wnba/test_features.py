from datetime import date
from sports.wnba.features import (
    compute_stat_avg, compute_stat_sigma_estimate, estimate_sigma,
    detect_b2b, parse_minutes,
)


def test_parse_minutes_handles_int_and_mmss():
    assert parse_minutes(34) == 34.0
    assert abs(parse_minutes("32:30") - 32.5) < 1e-6


def test_compute_stat_avg_from_recent_games():
    games = [
        {"PTS": 26, "REB": 8, "GAME_DATE": "MAY 18, 2026"},
        {"PTS": 18, "REB": 8, "GAME_DATE": "MAY 16, 2026"},
        {"PTS": 27, "REB": 10, "GAME_DATE": "MAY 14, 2026"},
    ]
    avg = compute_stat_avg(games, "PTS")
    assert abs(avg - 23.6667) < 1e-3


def test_compute_stat_sigma_estimate_uses_sample_std():
    games = [{"PTS": 20}, {"PTS": 22}, {"PTS": 24}, {"PTS": 26}, {"PTS": 28}]
    s = compute_stat_sigma_estimate(games, "PTS")
    assert abs(s - 3.162) < 0.01


def test_estimate_sigma_shrinks_when_sample_low():
    games = [{"PTS": 22}, {"PTS": 30}, {"PTS": 26}]
    s = estimate_sigma(games, stat="player_points", position="C")
    assert 4.0 < s < 4.7


def test_detect_b2b_true_for_one_day_apart():
    today = date(2026, 5, 19)
    games = [{"GAME_DATE": "MAY 18, 2026"}]
    assert detect_b2b(today, games) is True


def test_detect_b2b_false_for_two_days_apart():
    today = date(2026, 5, 19)
    games = [{"GAME_DATE": "MAY 17, 2026"}]
    assert detect_b2b(today, games) is False
