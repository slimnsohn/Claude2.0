from datetime import datetime
from core.types import BookOdds, Market, ResidualAdjustment


def test_book_odds_decimal_property():
    bo = BookOdds(book="pinnacle", american_odds=-110,
                  fetched_at=datetime(2026, 5, 19, 12, 0))
    assert abs(bo.decimal_odds - 1.9091) < 0.001


def test_book_odds_implied_prob():
    bo = BookOdds(book="pinnacle", american_odds=100,
                  fetched_at=datetime(2026, 5, 19))
    assert abs(bo.implied_prob - 0.5) < 1e-9


def test_market_construction():
    m = Market(
        event_id="evt-1", market_type="player_points",
        player_name="A'ja Wilson", line_value=22.5, side="over",
        commence_time=datetime(2026, 5, 19, 19, 30),
        is_alternate=False,
    )
    assert m.market_type == "player_points"
    assert m.is_alternate is False


def test_residual_adjustment_total():
    r = ResidualAdjustment(rest=-0.4, teammate_out=1.2)
    assert abs(r.total - 0.8) < 1e-9
