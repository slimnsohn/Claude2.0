"""NCAAF results via CollegeFootballData API."""
import os
from datetime import date, datetime, timezone
from dateutil import parser as dtparser
import requests

from odds_pipeline.results_sources.base import ResultsAdapter, GameResult

CFBD_BASE = "https://api.collegefootballdata.com"


def _fetch_games(year: int, week: int | None = None) -> list[dict]:
    key = os.environ.get("CFBD_API_KEY", "")
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    params = {"year": year, "division": "fbs"}
    if week:
        params["week"] = week
    r = requests.get(f"{CFBD_BASE}/games", params=params, headers=headers, timeout=30)
    return r.json()


def _parse_game(g: dict) -> GameResult | None:
    if g.get("completed") is not True:
        return None
    home_pts = int(g.get("home_points") or 0)
    away_pts = int(g.get("away_points") or 0)
    h_lines = g.get("home_line_scores") or []
    a_lines = g.get("away_line_scores") or []
    segs: dict[str, tuple[int, int]] = {}
    for i in range(min(4, len(h_lines), len(a_lines))):
        segs[f"Q{i+1}"] = (int(h_lines[i] or 0), int(a_lines[i] or 0))
    if "Q1" in segs and "Q2" in segs:
        segs["H1"] = (segs["Q1"][0] + segs["Q2"][0], segs["Q1"][1] + segs["Q2"][1])
    if "Q3" in segs and "Q4" in segs:
        segs["H2"] = (segs["Q3"][0] + segs["Q4"][0], segs["Q3"][1] + segs["Q4"][1])
    for i in range(4, len(h_lines)):
        segs[f"OT{i-3}"] = (int(h_lines[i] or 0), int(a_lines[i] or 0))
    segs["FULL"] = (home_pts, away_pts)
    commence = dtparser.isoparse(g["start_date"])
    return GameResult(
        sport="NCAAF", commence_time=commence,
        home_team_canonical=g["home_team"], away_team_canonical=g["away_team"],
        source_game_id=str(g["id"]),
        segment_scores=segs,
        went_to_ot=len(h_lines) > 4,
        raw_payload=g,
    )


class NCAAFResultsAdapter(ResultsAdapter):
    sport = "NCAAF"
    segments = ["FULL", "Q1", "Q2", "Q3", "Q4", "H1", "H2", "OT1", "OT2", "OT3"]

    def fetch_completed_games(self, date_from: date, date_to: date) -> list[GameResult]:
        years = {date_from.year, date_to.year}
        all_games: list[dict] = []
        for y in sorted(years):
            all_games.extend(_fetch_games(y))
        seen: set[str] = set()
        results: list[GameResult] = []
        for g in all_games:
            gid = str(g.get("id", ""))
            if gid in seen:
                continue
            seen.add(gid)
            try:
                commence = dtparser.isoparse(g["start_date"]).date()
            except Exception:
                continue
            if date_from <= commence <= date_to:
                r = _parse_game(g)
                if r:
                    results.append(r)
        return results
