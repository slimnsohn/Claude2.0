"""MLB results via MLB-StatsAPI."""
from datetime import date, timezone
from dateutil import parser as dtparser

from odds_pipeline.results_sources.base import ResultsAdapter, GameResult


def _schedule(start_date: str, end_date: str) -> list[dict]:
    import statsapi
    return statsapi.schedule(start_date=start_date, end_date=end_date)


def _linescore_data(game_pk: int) -> dict:
    import statsapi
    return statsapi.get("game_linescore", {"gamePk": game_pk})


class MLBResultsAdapter(ResultsAdapter):
    sport = "MLB"
    segments = ["FULL", "INN1", "INN2", "INN3", "INN4", "INN5",
                "INN6", "INN7", "INN8", "INN9", "F5"]

    def fetch_completed_games(self, date_from: date, date_to: date) -> list[GameResult]:
        sched = _schedule(date_from.isoformat(), date_to.isoformat())
        results: list[GameResult] = []
        for g in sched:
            if g.get("status") not in ("Final", "Game Over", "Completed Early"):
                continue
            game_pk = g["game_id"]
            data = _linescore_data(game_pk)
            innings = data.get("innings") or []
            segs: dict[str, tuple[int, int]] = {}
            for inn in innings:
                num = inn.get("num")
                h = int((inn.get("home") or {}).get("runs", 0) or 0)
                a = int((inn.get("away") or {}).get("runs", 0) or 0)
                if num and 1 <= num <= 9:
                    segs[f"INN{num}"] = (h, a)
            f5_h = sum(segs.get(f"INN{i}", (0, 0))[0] for i in range(1, 6))
            f5_a = sum(segs.get(f"INN{i}", (0, 0))[1] for i in range(1, 6))
            segs["F5"] = (f5_h, f5_a)
            teams = data.get("teams") or {}
            segs["FULL"] = (
                int((teams.get("home") or {}).get("runs", 0) or 0),
                int((teams.get("away") or {}).get("runs", 0) or 0),
            )
            commence = dtparser.isoparse(g["game_datetime"]).astimezone(timezone.utc)
            results.append(GameResult(
                sport="MLB",
                commence_time=commence,
                home_team_canonical=g["home_name"],
                away_team_canonical=g["away_name"],
                source_game_id=str(game_pk),
                segment_scores=segs,
                went_to_ot=len(innings) > 9,
                raw_payload={"schedule": g, "linescore": data},
            ))
        return results
