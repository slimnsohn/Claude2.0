"""NBA results via nba_api: per-quarter scores from BoxScoreSummaryV2."""
from datetime import date, datetime
from dateutil import parser as dtparser

from odds_pipeline.results_sources.base import ResultsAdapter, GameResult


def _list_games(date_from: date, date_to: date) -> list[dict]:
    from nba_api.stats.endpoints import leaguegamefinder
    df_str = date_from.strftime("%m/%d/%Y")
    dt_str = date_to.strftime("%m/%d/%Y")
    result = leaguegamefinder.LeagueGameFinder(
        date_from_nullable=df_str, date_to_nullable=dt_str,
        league_id_nullable="00",
    ).get_dict()
    rs = result["resultSets"][0]
    headers = rs["headers"]
    return [dict(zip(headers, row)) for row in rs["rowSet"]]


def _fetch_boxscore(game_id: str) -> dict:
    from nba_api.stats.endpoints import boxscoresummaryv2
    return boxscoresummaryv2.BoxScoreSummaryV2(game_id=game_id).get_dict()


def _parse_line_score(box: dict) -> dict[str, tuple[int, int]]:
    """LineScore result set: per-team rows with PTS_QTR1..4 (+ PTS_OT1..n)."""
    line_score = next(rs for rs in box["resultSets"] if rs["name"] == "LineScore")
    headers = line_score["headers"]
    rows = [dict(zip(headers, r)) for r in line_score["rowSet"]]
    # rows[0] = visitor (away), rows[1] = home — per NBA Stats convention
    away_row, home_row = rows[0], rows[1]
    segments: dict[str, tuple[int, int]] = {}
    for i in range(1, 5):
        key = f"Q{i}"
        h = int(home_row[f"PTS_QTR{i}"] or 0)
        a = int(away_row[f"PTS_QTR{i}"] or 0)
        segments[key] = (h, a)
    # Overtimes
    ot_idx = 1
    while f"PTS_OT{ot_idx}" in home_row:
        h = int(home_row[f"PTS_OT{ot_idx}"] or 0)
        a = int(away_row[f"PTS_OT{ot_idx}"] or 0)
        if h or a:
            segments[f"OT{ot_idx}"] = (h, a)
        ot_idx += 1
    # Halves
    q1h, q1a = segments["Q1"]
    q2h, q2a = segments["Q2"]
    q3h, q3a = segments["Q3"]
    q4h, q4a = segments["Q4"]
    segments["H1"] = (q1h + q2h, q1a + q2a)
    segments["H2"] = (q3h + q4h, q3a + q4a)
    segments["FULL"] = (int(home_row["PTS"]), int(away_row["PTS"]))
    return segments


class NBAResultsAdapter(ResultsAdapter):
    sport = "NBA"
    segments = ["FULL", "Q1", "Q2", "Q3", "Q4", "H1", "H2", "OT1", "OT2", "OT3", "OT4"]

    def fetch_completed_games(self, date_from: date, date_to: date) -> list[GameResult]:
        games_rows = _list_games(date_from, date_to)
        # rows are per-team; dedupe to one row per GAME_ID
        seen = {}
        for row in games_rows:
            gid = row["GAME_ID"]
            if gid not in seen:
                seen[gid] = row

        results: list[GameResult] = []
        for gid, row in seen.items():
            box = _fetch_boxscore(gid)
            segs = _parse_line_score(box)
            went_to_ot = any(k.startswith("OT") for k in segs)
            # Identify home/away from MATCHUP string ("LAL vs. BOS" = LAL home; "@" = away)
            matchup = row["MATCHUP"]
            if " vs. " in matchup:
                home, away = matchup.split(" vs. ")
            else:
                away, home = matchup.split(" @ ")
            commence = dtparser.isoparse(row["GAME_DATE"] + "T00:00:00Z")
            results.append(GameResult(
                sport="NBA",
                commence_time=commence,
                home_team_canonical=home.strip(),
                away_team_canonical=away.strip(),
                source_game_id=gid,
                segment_scores=segs,
                went_to_ot=went_to_ot,
                raw_payload=box,
            ))
        return results
