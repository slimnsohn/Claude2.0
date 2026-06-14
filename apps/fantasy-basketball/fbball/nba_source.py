"""Thin wrapper over nba_api PlayerGameLogs.

The NBA stats endpoint throttles hard and times out on stripped headers,
so every call goes through a retry-with-exponential-backoff guard. This is
the only module that touches the network.
"""

import time

import pandas as pd

# Community-standard polite floor between successful calls (seconds).
RATE_LIMIT_SECONDS = 0.7
# Per-request timeout handed to nba_api.
REQUEST_TIMEOUT = 60


def _retry(call, *, attempts: int, base_delay: float, sleeper=time.sleep):
    """Call `call()`, retrying on any exception with exponential backoff.

    Sleeps base_delay, 2*base_delay, 4*base_delay ... between attempts;
    no sleep after the final attempt. Re-raises the last error if all fail.
    """
    last_error = None
    for attempt in range(attempts):
        try:
            return call()
        except Exception as err:  # noqa: BLE001 - network errors are varied
            last_error = err
            if attempt < attempts - 1:
                sleeper(base_delay * (2 ** attempt))
    raise last_error


def fetch_season_logs(
    season: str,
    season_type: str = "Regular Season",
    *,
    attempts: int = 5,
    base_delay: float = 1.0,
    timeout: int = REQUEST_TIMEOUT,
) -> pd.DataFrame:
    """Pull the entire league's game logs for one season in a single call.

    Returns the raw nba_api dataframe (uppercase columns); normalization is
    the caller's job via fbball.transform.
    """
    # Imported lazily so unit tests for _retry don't need nba_api installed.
    from nba_api.stats.endpoints import PlayerGameLogs

    def call():
        return PlayerGameLogs(
            season_nullable=season,
            season_type_nullable=season_type,
            timeout=timeout,
        ).get_data_frames()[0]

    return _retry(call, attempts=attempts, base_delay=base_delay)
