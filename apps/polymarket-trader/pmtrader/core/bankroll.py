"""Bankroll policy: equity accounting, day-P&L baseline, double-or-bust mode.

The double-or-bust stopping rule changes WHEN the run ends, never HOW sizing
works — gambling harder when behind is exactly the failure mode this system
exists to avoid.
"""
from __future__ import annotations

from enum import StrEnum


class RunVerdict(StrEnum):
    CONTINUE = "CONTINUE"
    STOP_WON = "STOP_WON"    # equity >= 2x start
    STOP_LOST = "STOP_LOST"  # equity <= floor (5% of start by default)


class Bankroll:
    def __init__(self, starting_equity: float, double_or_bust: bool = True,
                 win_multiple: float = 2.0, loss_floor_frac: float = 0.05):
        self.starting_equity = starting_equity
        self.double_or_bust = double_or_bust
        self.win_multiple = win_multiple
        self.loss_floor_frac = loss_floor_frac
        self._day_key: int | None = None
        self._day_baseline: float = starting_equity

    @staticmethod
    def equity(cash: float, position_marks: dict[str, float]) -> float:
        return cash + sum(position_marks.values())

    def check(self, equity: float) -> RunVerdict:
        if not self.double_or_bust:
            return RunVerdict.CONTINUE
        if equity >= self.starting_equity * self.win_multiple:
            return RunVerdict.STOP_WON
        if equity <= self.starting_equity * self.loss_floor_frac:
            return RunVerdict.STOP_LOST
        return RunVerdict.CONTINUE

    def progress(self, equity: float) -> float:
        """0.0 at start, 1.0 at the win target (clamped)."""
        target = self.starting_equity * self.win_multiple
        span = target - self.starting_equity
        return max(0.0, min(1.0, (equity - self.starting_equity) / span))

    def mark_day(self, ts: float, equity: float) -> None:
        """Call periodically; resets the day-P&L baseline at UTC midnight."""
        day = int(ts // 86_400)
        if day != self._day_key:
            self._day_key = day
            self._day_baseline = equity

    def day_pnl(self, equity: float) -> float:
        return equity - self._day_baseline
