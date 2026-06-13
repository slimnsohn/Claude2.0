"""WNBA feature extraction from stats.wnba.com playergamelog rows."""
from __future__ import annotations
import json
import statistics
from datetime import date, datetime, timedelta
from pathlib import Path

PRIORS = json.loads((Path(__file__).with_name("league_priors.json")).read_text())

STAT_TO_COL = {
    "player_points": "PTS",
    "player_rebounds": "REB",
    "player_assists": "AST",
    "player_threes": "FG3M",
}


def parse_minutes(v) -> float:
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str) and ":" in v:
        m, s = v.split(":")
        return int(m) + int(s) / 60.0
    return float(v)


def parse_game_date(s: str) -> date:
    return datetime.strptime(s, "%b %d, %Y").date()


def compute_stat_avg(games: list[dict], col: str) -> float:
    vals = [float(g[col]) for g in games if col in g]
    if not vals:
        return 0.0
    return sum(vals) / len(vals)


def compute_stat_sigma_estimate(games: list[dict], col: str) -> float:
    vals = [float(g[col]) for g in games if col in g]
    if len(vals) < 2:
        return 0.0
    return statistics.stdev(vals)


def estimate_sigma(games: list[dict], stat: str, position: str,
                    min_sample_for_player: int = 5) -> float:
    col = STAT_TO_COL.get(stat)
    if not col:
        raise ValueError(f"Unknown stat: {stat}")
    league_sigma = PRIORS["league_sigma_by_stat"][stat].get(
        position, PRIORS["league_sigma_by_stat"][stat]["G"]
    )
    n = len(games)
    if n < 2:
        return league_sigma
    player_sigma = compute_stat_sigma_estimate(games, col)
    if n >= min_sample_for_player:
        return max(player_sigma, 0.5)
    w = n / (n + min_sample_for_player)
    blended = w * player_sigma + (1.0 - w) * league_sigma
    return max(blended, 0.5)


def detect_b2b(today: date, recent_games: list[dict]) -> bool:
    yesterday = today - timedelta(days=1)
    for g in recent_games:
        if "GAME_DATE" in g and parse_game_date(g["GAME_DATE"]) == yesterday:
            return True
    return False


def compute_rest_days(today: date, recent_games: list[dict]) -> int:
    if not recent_games:
        return 99
    last = max(parse_game_date(g["GAME_DATE"]) for g in recent_games if "GAME_DATE" in g)
    return (today - last).days
