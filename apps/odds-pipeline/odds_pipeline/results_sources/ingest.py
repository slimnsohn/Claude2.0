"""Results ingest: call the per-sport adapter and archive each GameResult as JSON."""
from dataclasses import dataclass, field
from datetime import date
import json

from odds_pipeline import archive
from odds_pipeline.identity import matcher
from odds_pipeline.results_sources.base import ResultsAdapter


@dataclass
class ResultsPullResult:
    games_archived: int = 0
    errors: list[str] = field(default_factory=list)


def pull_results_for_sport(
    *,
    adapter: ResultsAdapter,
    sport: str,
    date_from: date,
    date_to: date,
    archive_root: str,
) -> ResultsPullResult:
    result = ResultsPullResult()
    try:
        games = adapter.fetch_completed_games(date_from, date_to)
    except Exception as e:
        result.errors.append(f"{sport} fetch: {e}")
        return result

    for g in games:
        game_id = matcher.build_game_id(
            sport=sport,
            commence_time=g.commence_time,
            home=g.home_team_canonical,
            away=g.away_team_canonical,
        )
        payload = {
            "game_id": game_id,
            "sport": sport,
            "commence_time": g.commence_time.isoformat(),
            "home_team_canonical": g.home_team_canonical,
            "away_team_canonical": g.away_team_canonical,
            "source_game_id": g.source_game_id,
            "segment_scores": {k: list(v) for k, v in g.segment_scores.items()},
            "went_to_ot": g.went_to_ot,
            "raw_payload": json.loads(json.dumps(g.raw_payload, default=str)),
        }
        archive.write_results(
            root=archive_root, sport=sport, game_id=game_id, payload=payload,
        )
        result.games_archived += 1
    return result
