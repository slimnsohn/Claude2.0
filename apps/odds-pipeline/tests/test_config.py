import os
import pytest
from odds_pipeline import config


def test_sport_markets_covers_all_six_sports():
    expected = {"NBA", "NFL", "NHL", "MLB", "NCAAB", "NCAAF"}
    assert set(config.SPORT_MARKETS.keys()) == expected


def test_nba_markets_include_quarters_and_halves():
    nba = config.SPORT_MARKETS["NBA"]
    assert "h2h" in nba
    assert "spreads" in nba
    assert "totals" in nba
    assert "spreads_q1" in nba
    assert "totals_q1" in nba
    assert "spreads_h1" in nba
    assert "totals_h1" in nba


def test_nhl_uses_period_markets_not_quarters():
    nhl = config.SPORT_MARKETS["NHL"]
    assert "spreads_q1" not in nhl
    # Exact key name verified empirically on first pull; placeholder accepted here
    assert any("p1" in m or "period" in m for m in nhl)


def test_ncaab_has_no_quarter_markets():
    ncaab = config.SPORT_MARKETS["NCAAB"]
    assert "spreads_q1" not in ncaab
    assert "spreads_h1" in ncaab


def test_api_key_loaded_from_env(monkeypatch):
    monkeypatch.setenv("THE_ODDS_API_KEY", "test-key-123")
    # Force reimport so config re-reads env
    import importlib
    importlib.reload(config)
    assert config.THE_ODDS_API_KEY == "test-key-123"
