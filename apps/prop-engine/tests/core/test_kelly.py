import pytest
from core.kelly import fractional_kelly_stake


def test_capped_at_max_stake_pct():
    # p=0.55, +110: full Kelly ~ 14.1%, quarter Kelly ~ 3.5%
    # Bankroll $10k → $352 raw, capped at 2% = $200
    stake = fractional_kelly_stake(
        posterior_prob=0.55, american_odds=110,
        bankroll=10000, kelly_fraction=0.25, max_stake_pct=0.02, min_bet=5,
    )
    assert abs(stake - 200.0) < 1e-6


def test_uncapped_below_max():
    # p=0.52, +100: full Kelly = 4%, quarter Kelly = 1%, $10k → $100 (under 2% cap)
    stake = fractional_kelly_stake(
        posterior_prob=0.52, american_odds=100,
        bankroll=10000, kelly_fraction=0.25, max_stake_pct=0.02, min_bet=5,
    )
    assert abs(stake - 100.0) < 1e-6


def test_zero_when_no_edge():
    stake = fractional_kelly_stake(
        posterior_prob=0.50, american_odds=-110,
        bankroll=10000, kelly_fraction=0.25, max_stake_pct=0.02, min_bet=5,
    )
    assert stake == 0.0


def test_zero_when_below_min_bet():
    stake = fractional_kelly_stake(
        posterior_prob=0.501, american_odds=-110,
        bankroll=100, kelly_fraction=0.25, max_stake_pct=0.02, min_bet=5,
    )
    assert stake == 0.0


def test_raises_on_invalid_bankroll():
    with pytest.raises(ValueError):
        fractional_kelly_stake(0.55, 100, bankroll=0, kelly_fraction=0.25,
                               max_stake_pct=0.02, min_bet=5)
