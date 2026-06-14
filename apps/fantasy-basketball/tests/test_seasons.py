import datetime as dt

from fbball import seasons


def test_current_season_midseason_fall():
    # November 2025 -> the 2025-26 season is underway
    assert seasons.current_season(dt.date(2025, 11, 15)) == "2025-26"


def test_current_season_spring_belongs_to_prior_start_year():
    # June 2026 is still the tail (playoffs) of the 2025-26 season
    assert seasons.current_season(dt.date(2026, 6, 14)) == "2025-26"


def test_current_season_summer_offseason_rolls_to_prior():
    # September 2025, before the Oct tip-off, is still 2024-25
    assert seasons.current_season(dt.date(2025, 9, 1)) == "2024-25"


def test_recent_seasons_returns_n_chronological():
    out = seasons.recent_seasons(4, today=dt.date(2026, 6, 14))
    assert out == ["2022-23", "2023-24", "2024-25", "2025-26"]


def test_recent_seasons_single():
    assert seasons.recent_seasons(1, today=dt.date(2025, 11, 15)) == ["2025-26"]
