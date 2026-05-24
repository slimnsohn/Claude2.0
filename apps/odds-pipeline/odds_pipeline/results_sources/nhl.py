"""NHL results via NHL Stats API (api-web.nhle.com), no auth required."""
from datetime import date, datetime, timezone, timedelta
from dateutil import parser as dtparser
import requests

from odds_pipeline.results_sources.base import ResultsAdapter, GameResult

SCHEDULE_URL = "https://api-web.nhle.com/v1/schedule/{date}"
BOXSCORE_URL = "https://api-web.nhle.com/v1/gamecenter/{game_id}/boxscore"


def _fetch_schedule(date_str: str) -> dict:
    return requests.get(SCHEDULE_URL.format(date=date_str), timeout=30).json()


def _fetch_boxscore(game_id: int | str) -> dict:
    return requests.get(BOXSCORE_URL.format(game_id=game_id), timeout=30).json()


def _parse_boxscore(box: dict) -> tuple[dict[str, tuple[int, int]], bool]:
    """Parse periodDescriptor entries from box['summary']['linescore']['byPeriod']."""
    summary = box.get("summary") or box
    linescore = summary.get("linescore") or {}
    by_period = linescore.get("byPeriod") or []
    segs: dict[str, tuple[int, int]] = {}
    went_to_ot = False
    for p in by_period:
        desc = p.get("periodDescriptor") or {}
        num = desc.get("number")
        ptype = desc.get("periodType", "REG")
        h = int(p.get("home", 0))
        a = int(p.get("away", 0))
        if ptype == "REG":
            segs[f"P{num}"] = (h, a)
        elif ptype == "OT":
            key = f"OT{num - 3}" if num and num > 3 else "OT1"
            segs[key] = (h, a)
            went_to_ot = True
        elif ptype == "SO":
            segs["SO"] = (h, a)
            went_to_ot = True
    total = linescore.get("totals", {})
    segs["FULL"] = (int(total.get("home", 0)), int(total.get("away", 0)))
    return segs, went_to_ot


class NHLResultsAdapter(ResultsAdapter):
    sport = "NHL"
    segments = ["FULL", "P1", "P2", "P3", "OT1", "SO"]

    def fetch_completed_games(self, date_from: date, date_to: date) -> list[GameResult]:
        results: list[GameResult] = []
        cur = date_from
        while cur <= date_to:
            sched = _fetch_schedule(cur.isoformat())
            for game_day in sched.get("gameWeek", []):
                if game_day.get("date") != cur.isoformat():
                    continue
                for g in game_day.get("games", []):
                    if g.get("gameState") not in ("OFF", "FINAL"):
                        continue
                    box = _fetch_boxscore(g["id"])
                    segs, ot = _parse_boxscore(box)
                    commence = dtparser.isoparse(g["startTimeUTC"])
                    home = g.get("homeTeam", {}).get("abbrev", "")
                    away = g.get("awayTeam", {}).get("abbrev", "")
                    results.append(GameResult(
                        sport="NHL", commence_time=commence,
                        home_team_canonical=home, away_team_canonical=away,
                        source_game_id=str(g["id"]),
                        segment_scores=segs, went_to_ot=ot,
                        raw_payload=box,
                    ))
            cur += timedelta(days=1)
        return results
