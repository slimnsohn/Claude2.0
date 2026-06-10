import pytest

from pmtrader.core.bankroll import Bankroll, RunVerdict


class TestEquity:
    def test_equity_cash_plus_marks(self):
        b = Bankroll(starting_equity=1000.0)
        eq = b.equity(cash=400.0, position_marks={"t1": 350.0, "t2": 200.0})
        assert eq == pytest.approx(950.0)


class TestDoubleOrBust:
    def test_continue_in_range(self):
        b = Bankroll(starting_equity=1000.0)
        assert b.check(1500.0) == RunVerdict.CONTINUE

    def test_stop_won_at_double(self):
        b = Bankroll(starting_equity=1000.0)
        assert b.check(2000.0) == RunVerdict.STOP_WON
        assert b.check(2400.0) == RunVerdict.STOP_WON

    def test_stop_lost_at_floor(self):
        b = Bankroll(starting_equity=1000.0)
        assert b.check(50.0) == RunVerdict.STOP_LOST
        assert b.check(30.0) == RunVerdict.STOP_LOST

    def test_just_above_floor_continues(self):
        b = Bankroll(starting_equity=1000.0)
        assert b.check(51.0) == RunVerdict.CONTINUE

    def test_disabled_mode_never_stops(self):
        b = Bankroll(starting_equity=1000.0, double_or_bust=False)
        assert b.check(5000.0) == RunVerdict.CONTINUE
        assert b.check(10.0) == RunVerdict.CONTINUE

    def test_progress_fraction(self):
        b = Bankroll(starting_equity=1000.0)
        assert b.progress(1500.0) == pytest.approx(0.5)
        assert b.progress(1000.0) == pytest.approx(0.0)
        assert b.progress(2000.0) == pytest.approx(1.0)


class TestDayPnl:
    def test_day_pnl_tracks_within_day(self):
        b = Bankroll(starting_equity=1000.0)
        b.mark_day(ts=0.0, equity=1000.0)
        assert b.day_pnl(equity=950.0) == pytest.approx(-50.0)

    def test_day_boundary_resets(self):
        b = Bankroll(starting_equity=1000.0)
        b.mark_day(ts=0.0, equity=1000.0)
        b.mark_day(ts=86_401.0, equity=950.0)  # next utc day
        assert b.day_pnl(equity=940.0) == pytest.approx(-10.0)

    def test_same_day_no_reset(self):
        b = Bankroll(starting_equity=1000.0)
        b.mark_day(ts=0.0, equity=1000.0)
        b.mark_day(ts=3600.0, equity=900.0)  # same day: baseline unchanged
        assert b.day_pnl(equity=900.0) == pytest.approx(-100.0)
