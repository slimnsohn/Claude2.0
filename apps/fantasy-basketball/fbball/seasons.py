"""NBA season-label helpers. A season is labeled by its start year: the
2025-26 season tips off Oct 2025 and ends (playoffs) Jun 2026.
"""

import datetime as dt

# NBA seasons tip off in October.
SEASON_START_MONTH = 10


def _start_year(today: dt.date) -> int:
    """The start year of the season that `today` falls in."""
    if today.month >= SEASON_START_MONTH:
        return today.year
    return today.year - 1


def current_season(today: dt.date) -> str:
    start = _start_year(today)
    return f"{start}-{str(start + 1)[-2:]}"


def recent_seasons(n: int, today: dt.date) -> list[str]:
    """The n most recent seasons, oldest first, including the current one."""
    start = _start_year(today)
    years = range(start - n + 1, start + 1)
    return [f"{y}-{str(y + 1)[-2:]}" for y in years]
