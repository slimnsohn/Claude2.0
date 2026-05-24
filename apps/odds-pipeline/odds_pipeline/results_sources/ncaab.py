"""NCAAB results via ESPN scoreboard JSON."""
from datetime import date, timedelta
import requests
from dateutil import parser as dtparser

from odds_pipeline.results_sources.base import ResultsAdapter, GameResult

URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard"


def _fetch_scoreboard(date_str: str) -> dict:
    return requests.get(URL, params={"dates": date_str}, timeout=30).json()


def _parse_event(evt: dict) -> GameResult | None:
    competition = evt["competitions"][0]
    status = (evt.get("status") or {}).get("type", {}).get("state")
    if status != "post":
        return None
    competitors = competition["competitors"]
    home = next(c for c in competitors if c["homeAway"] == "home")
    away = next(c for c in competitors if c["homeAway"] == "away")
    home_linescores = [int(x["value"]) for x in (home.get("linescores") or [])]
    away_linescores = [int(x["value"]) for x in (away.get("linescores") or [])]
    segs: dict[str, tuple[int, int]] = {}
    if len(home_linescores) >= 2 and len(away_linescores) >= 2:
        segs["H1"] = (home_linescores[0], away_linescores[0])
        segs["H2"] = (home_linescores[1], away_linescores[1])
    for i in range(2, max(len(home_linescores), len(away_linescores))):
        h = home_linescores[i] if i < len(home_linescores) else 0
        a = away_linescores[i] if i < len(away_linescores) else 0
        segs[f"OT{i - 1}"] = (h, a)
    segs["FULL"] = (int(home["score"]), int(away["score"]))
    commence = dtparser.isoparse(evt["date"])
    return GameResult(
        sport="NCAAB",
        commence_time=commence,
        home_team_canonical=home["team"]["abbreviation"],
        away_team_canonical=away["team"]["abbreviation"],
        source_game_id=str(evt["id"]),
        segment_scores=segs,
        went_to_ot=len(home_linescores) > 2,
        raw_payload=evt,
    )


class NCAABResultsAdapter(ResultsAdapter):
    sport = "NCAAB"
    segments = ["FULL", "H1", "H2", "OT1", "OT2"]

    def fetch_completed_games(self, date_from: date, date_to: date) -> list[GameResult]:
        results: list[GameResult] = []
        cur = date_from
        while cur <= date_to:
            payload = _fetch_scoreboard(cur.strftime("%Y%m%d"))
            for evt in payload.get("events", []):
                r = _parse_event(evt)
                if r:
                    results.append(r)
            cur += timedelta(days=1)
        return results
