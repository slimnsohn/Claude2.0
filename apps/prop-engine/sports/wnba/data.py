"""stats.wnba.com adapter — same NBA stats backend with LeagueID=10.

Requires specific browser-style headers or Cloudflare returns 403.
"""
from __future__ import annotations
import requests

BASE = "https://stats.wnba.com/stats"

REQUIRED_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.wnba.com/",
    "Origin": "https://www.wnba.com",
    "x-nba-stats-origin": "stats",
    "x-nba-stats-token": "true",
    "Host": "stats.wnba.com",
    "Connection": "keep-alive",
}


class StatsWnbaClient:
    def __init__(self, base: str = BASE, timeout: float = 15.0):
        self.base = base
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(REQUIRED_HEADERS)

    def _get(self, endpoint: str, params: dict) -> dict:
        r = self.session.get(f"{self.base}/{endpoint}", params=params, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    @staticmethod
    def _zip_rows(result_set: dict) -> list[dict]:
        headers = result_set["headers"]
        return [dict(zip(headers, row)) for row in result_set["rowSet"]]

    def player_game_log(self, player_id: int, season: str,
                          season_type: str = "Regular Season") -> list[dict]:
        payload = self._get("playergamelog", {
            "PlayerID": player_id,
            "Season": season,
            "SeasonType": season_type,
            "LeagueID": "10",
            "DateFrom": "",
            "DateTo": "",
        })
        return self._zip_rows(payload["resultSets"][0])

    def common_all_players(self, season: str) -> list[dict]:
        payload = self._get("commonallplayers", {
            "LeagueID": "10",
            "Season": season,
            "IsOnlyCurrentSeason": 1,
        })
        return self._zip_rows(payload["resultSets"][0])
