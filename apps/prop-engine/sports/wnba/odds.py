"""The Odds API client for WNBA player props."""
from __future__ import annotations
import os
from datetime import datetime
from typing import Optional
import requests

BASE = "https://api.the-odds-api.com/v4"
SPORT_KEY = "basketball_wnba"
DEFAULT_MARKETS = [
    "player_points", "player_rebounds", "player_assists", "player_threes",
    "player_points_alternate", "player_rebounds_alternate",
    "player_assists_alternate", "player_threes_alternate",
]
DEFAULT_BOOKS = ["pinnacle", "fanduel", "bookmaker", "betonline", "draftkings"]


class OddsAPIClient:
    def __init__(self, api_key: Optional[str] = None, base: str = BASE, timeout: float = 15.0):
        self.api_key = api_key or os.environ.get("ODDS_API_KEY")
        if not self.api_key:
            raise RuntimeError("ODDS_API_KEY not set in env or constructor")
        self.base = base
        self.timeout = timeout

    def fetch_events(self) -> list[dict]:
        url = f"{self.base}/sports/{SPORT_KEY}/events"
        r = requests.get(url, params={"apiKey": self.api_key}, timeout=self.timeout)
        r.raise_for_status()
        out = []
        for ev in r.json():
            out.append({
                "event_id": ev["id"],
                "commence_time": ev["commence_time"],
                "home_team": ev["home_team"],
                "away_team": ev["away_team"],
            })
        return out

    def fetch_event_player_props(
        self, event_id: str,
        markets: Optional[list[str]] = None,
        bookmakers: Optional[list[str]] = None,
    ) -> list[dict]:
        url = f"{self.base}/sports/{SPORT_KEY}/events/{event_id}/odds"
        params = {
            "apiKey": self.api_key,
            "regions": "us",
            "markets": ",".join(markets or DEFAULT_MARKETS),
            "oddsFormat": "american",
            "bookmakers": ",".join(bookmakers or DEFAULT_BOOKS),
        }
        r = requests.get(url, params=params, timeout=self.timeout)
        r.raise_for_status()
        payload = r.json()

        rows = []
        commence = payload["commence_time"]
        for bm in payload.get("bookmakers", []):
            book = bm["key"]
            fetched = bm.get("last_update") or datetime.utcnow().isoformat()
            for m in bm.get("markets", []):
                market_key = m["key"]
                is_alt = market_key.endswith("_alternate")
                base_market = market_key.replace("_alternate", "")
                for o in m.get("outcomes", []):
                    side = (o.get("name") or "").lower()
                    if side not in ("over", "under"):
                        continue
                    rows.append({
                        "event_id": payload["id"],
                        "commence_time": commence,
                        "market_type": base_market,
                        "player_name": o.get("description") or o.get("participant") or "",
                        "line_value": float(o["point"]),
                        "side": side,
                        "book": book,
                        "american_odds": int(o["price"]),
                        "fetched_at": fetched,
                        "is_alternate": is_alt,
                    })
        return rows
