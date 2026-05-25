"""NFL results via nfl_data_py.

NOTE: nfl_data_py.import_schedules() only exposes full-game scores
(`home_score`, `away_score`). It does NOT have per-quarter score columns.
Per-quarter NFL scores need a different source (ESPN scoreboard or
nfl_data_py.import_pbp_data aggregated by qtr). This adapter therefore
emits ONLY the FULL segment. Per-quarter/half adds are a v2 follow-up.

Per the workspace rule "missing data shows as missing", we do NOT emit
(0, 0) for Q1-Q4/H1/H2 — they're simply absent from segment_scores.
"""
from datetime import date, datetime, timezone
import pandas as pd

from odds_pipeline.results_sources.base import ResultsAdapter, GameResult


def _import_schedules(seasons: list[int]) -> pd.DataFrame:
    import nfl_data_py as nfl
    return nfl.import_schedules(seasons)


def _row_to_result(row: pd.Series) -> GameResult:
    # Only FULL is reliably available from import_schedules.
    segs: dict[str, tuple[int, int]] = {
        "FULL": (int(row["home_score"]), int(row["away_score"])),
    }
    went_to_ot = bool(int(row.get("overtime") or 0))
    commence = datetime.fromisoformat(str(row["gameday"])).replace(tzinfo=timezone.utc)
    return GameResult(
        sport="NFL",
        commence_time=commence,
        home_team_canonical=str(row["home_team"]),
        away_team_canonical=str(row["away_team"]),
        source_game_id=str(row["game_id"]),
        segment_scores=segs,
        went_to_ot=went_to_ot,
        raw_payload=row.to_dict(),
    )


class NFLResultsAdapter(ResultsAdapter):
    sport = "NFL"
    segments = ["FULL", "Q1", "Q2", "Q3", "Q4", "H1", "H2", "OT1"]

    def fetch_completed_games(self, date_from: date, date_to: date) -> list[GameResult]:
        seasons = list(range(date_from.year - 1, date_to.year + 1))
        df = _import_schedules(seasons)
        mask = pd.to_datetime(df["gameday"]).between(
            pd.Timestamp(date_from), pd.Timestamp(date_to)
        )
        sub = df[mask & df["home_score"].notna()]
        return [_row_to_result(r) for _, r in sub.iterrows()]
