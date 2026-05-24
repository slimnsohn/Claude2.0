"""The Odds API HTTP client with rate-limit retries and credit tracking."""
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import requests

BASE_URL = "https://api.the-odds-api.com/v4"
BACKOFF_SECONDS = [1, 4, 16]


@dataclass
class Usage:
    requests_used: int
    requests_remaining: Optional[int]
    last_cost: Optional[int]


class TheOddsApiClient:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def _get(self, path: str, params: dict) -> tuple[dict | list, Usage]:
        params = {**params, "apiKey": self.api_key}
        url = f"{BASE_URL}{path}"
        last_err = None
        for delay in BACKOFF_SECONDS + [None]:
            resp = requests.get(url, params=params, timeout=30)
            if resp.status_code == 200:
                u = Usage(
                    requests_used=int(resp.headers.get("x-requests-used", 0)),
                    requests_remaining=int(resp.headers["x-requests-remaining"])
                        if "x-requests-remaining" in resp.headers else None,
                    last_cost=int(resp.headers["x-requests-last"])
                        if "x-requests-last" in resp.headers else None,
                )
                return resp.json(), u
            if resp.status_code == 429 and delay is not None:
                time.sleep(delay)
                continue
            last_err = f"HTTP {resp.status_code}: {resp.text[:200]}"
            break
        raise RuntimeError(f"Odds API call failed: {last_err}")

    def get_historical_events(self, sport_key: str, date: datetime) -> tuple[list, Usage]:
        body, usage = self._get(
            f"/historical/sports/{sport_key}/events",
            {"date": date.strftime("%Y-%m-%dT%H:%M:%SZ")},
        )
        # Historical endpoints wrap list payloads in {"data": [...], "timestamp": ...}
        events = body.get("data", []) if isinstance(body, dict) else body
        return events, usage

    def get_historical_event_odds(
        self, sport_key: str, event_id: str, date: datetime,
        regions: list[str], markets: list[str],
    ) -> tuple[dict, Usage]:
        # Per-event endpoint returns the full envelope; let the caller unwrap as needed
        # (the archive layer stores the whole envelope for provenance).
        return self._get(
            f"/historical/sports/{sport_key}/events/{event_id}/odds",
            {
                "date": date.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "regions": ",".join(regions),
                "markets": ",".join(markets),
                "oddsFormat": "american",
            },
        )
