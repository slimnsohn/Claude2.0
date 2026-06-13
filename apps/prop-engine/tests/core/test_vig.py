import pytest
from core.vig import (
    american_to_implied, devig_two_way_shin, devig_two_way_power,
    enforce_monotonic_ladder,
)


def test_american_to_implied_underdog():
    assert abs(american_to_implied(150) - 0.40) < 1e-6


def test_american_to_implied_favorite():
    assert abs(american_to_implied(-150) - 0.60) < 1e-6


def test_american_to_implied_pickem():
    assert abs(american_to_implied(100) - 0.50) < 1e-6


def test_devig_two_way_power_balanced():
    p_over, p_under = devig_two_way_power(-110, -110)
    assert abs(p_over - 0.5) < 1e-6
    assert abs(p_under - 0.5) < 1e-6


def test_devig_two_way_power_lopsided():
    p_over, p_under = devig_two_way_power(200, -250)
    assert abs(p_over - 0.3182) < 1e-3
    assert abs(p_over + p_under - 1.0) < 1e-9


def test_devig_two_way_shin_balanced_matches_power():
    p_over_s, p_under_s = devig_two_way_shin(-110, -110)
    assert abs(p_over_s - 0.5) < 1e-4
    assert abs(p_under_s - 0.5) < 1e-4


def test_devig_two_way_shin_compresses_longshot():
    p_over_p, _ = devig_two_way_power(200, -250)
    p_over_s, _ = devig_two_way_shin(200, -250)
    assert p_over_s < p_over_p
    p_over_s2, p_under_s2 = devig_two_way_shin(200, -250)
    assert abs(p_over_s2 + p_under_s2 - 1.0) < 1e-6


def test_devig_no_vig_market_returns_implied():
    p_over, p_under = devig_two_way_shin(100, -100)
    assert abs(p_over - 0.5) < 1e-6


def test_american_to_implied_raises_on_invalid():
    with pytest.raises(ValueError):
        american_to_implied(0)
    with pytest.raises(ValueError):
        american_to_implied(50)


def test_enforce_monotonic_ladder_pava():
    fair_probs = [0.80, 0.55, 0.65]
    fixed = enforce_monotonic_ladder(fair_probs)
    assert all(fixed[i] >= fixed[i + 1] for i in range(len(fixed) - 1))
    assert abs(fixed[0] - 0.80) < 1e-6
    assert abs(fixed[1] - 0.60) < 1e-6
    assert abs(fixed[2] - 0.60) < 1e-6
