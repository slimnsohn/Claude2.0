"""NFL results via nfl_data_py (nflfastR schedules with per-quarter columns)."""
from datetime import date, datetime, timezone
import pandas as pd

from odds_pipeline.results_sources.base import ResultsAdapter, GameResult


def _import_schedules(seasons: list[int]) -> pd.DataFrame:
    import nfl_data_py as nfl
    return nfl.import_schedules(seasons)


def _row_to_result(row: pd.Series) -> GameResult:
    segs: dict[str, tuple[int, int]] = {}
    for q in range(1, 5):
        h = int(row.get(f"home_score_q{q}") or 0)
        a = int(row.get(f"away_score_q{q}") or 0)
        segs[f"Q{q}"] = (h, a)
    segs["H1"] = (segs["Q1"][0] + segs["Q2"][0], segs["Q1"][1] + segs["Q2"][1])
    segs["H2"] = (segs["Q3"][0] + segs["Q4"][0], segs["Q3"][1] + segs["Q4"][1])
    if pd.notna(row.get("overtime")) and int(row.get("overtime") or 0) == 1:
        ot_h = int(row["home_score"]) - sum(segs[f"Q{i}"][0] for i in range(1, 5))
        ot_a = int(row["away_score"]) - sum(segs[f"Q{i}"][1] for i in range(1, 5))
        if ot_h or ot_a:
            segs["OT1"] = (ot_h, ot_a)
    segs["FULL"] = (int(row["home_score"]), int(row["away_score"]))
    commence = datetime.fromisoformat(str(row["gameday"])).replace(tzinfo=timezone.utc)
    return GameResult(
        sport="NFL",
        commence_time=commence,
        home_team_canonical=str(row["home_team"]),
        away_team_canonical=str(row["away_team"]),
        source_game_id=str(row["game_id"]),
        segment_scores=segs,
        went_to_ot=bool(int(row.get("overtime") or 0)),
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
