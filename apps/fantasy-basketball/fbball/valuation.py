"""9-cat z-score valuation — ported from the prior build's zscore.py onto the
live DuckDB views.

Two non-negotiable refinements (per the build spec):
  - Punt-aware: zeroing a category out of the total re-ranks for that build.
  - Volume-weighted percentage cats: FG%/FT% use the IMPACT method
    ((player_pct - league_pct) * attempts_per_game), z-scored — never the raw
    percentage, which over-rewards low-volume specialists.
"""

import statistics

# 9-cat order. Maps each category to its column in player_season_stats /
# player_recent_form. Percentage cats carry their per-game attempts column.
CATS = ["FG_PCT", "FT_PCT", "FG3M", "PTS", "REB", "AST", "STL", "BLK", "TOV"]

CAT_COLUMN = {
    "FG3M": "tpm_pg", "PTS": "ppg", "REB": "rpg", "AST": "apg",
    "STL": "spg", "BLK": "bpg", "TOV": "topg",
    "FG_PCT": "fg_pct", "FT_PCT": "ft_pct",
}
PCT_CATS = {"FG_PCT", "FT_PCT"}
NEGATIVE_CATS = {"TOV"}  # lower is better -> z-score inverted

# (per-game attempts, total makes, total attempts) for the impact method
PCT_COMPONENTS = {
    "FG_PCT": ("fga_pg", "fgm_tot", "fga_tot"),
    "FT_PCT": ("fta_pg", "ftm_tot", "fta_tot"),
}

CAT_DISPLAY = {
    "FG_PCT": "FG%", "FT_PCT": "FT%", "FG3M": "3PM", "PTS": "PTS", "REB": "REB",
    "AST": "AST", "STL": "STL", "BLK": "BLK", "TOV": "TO",
}


def _num(x) -> float:
    """Coerce DB NULL / NaN (e.g. a percentage with zero attempts) to 0.0."""
    if x is None:
        return 0.0
    x = float(x)
    return 0.0 if x != x else x   # x != x is True only for NaN


def _safe_std(values: list[float]) -> float:
    if len(values) < 2:
        return 1.0
    s = statistics.stdev(values)
    return s if s > 0 else 1.0


def _impact(player: dict, cat: str, league_pct: float) -> float:
    att_col = PCT_COMPONENTS[cat][0]
    return (_num(player.get(CAT_COLUMN[cat])) - league_pct) * _num(player.get(att_col))


def league_averages(players: list[dict]) -> dict:
    """Per-category baselines: mean/std for counting cats, league_pct +
    impact mean/std for percentage cats."""
    avgs = {}
    for cat in CATS:
        if cat in PCT_CATS:
            _, made_tot, att_tot = PCT_COMPONENTS[cat]
            total_made = sum(_num(p.get(made_tot)) for p in players)
            total_att = sum(_num(p.get(att_tot)) for p in players)
            league_pct = total_made / total_att if total_att > 0 else 0.0
            impacts = [_impact(p, cat, league_pct) for p in players]
            avgs[cat] = {
                "league_pct": league_pct,
                "mean": statistics.mean(impacts) if impacts else 0.0,
                "std": _safe_std(impacts),
            }
        else:
            col = CAT_COLUMN[cat]
            vals = [_num(p.get(col)) for p in players]
            avgs[cat] = {
                "mean": statistics.mean(vals) if vals else 0.0,
                "std": _safe_std(vals),
            }
    return avgs


def _zscore(player: dict, cat: str, avgs: dict) -> float:
    a = avgs[cat]
    if cat in PCT_CATS:
        return (_impact(player, cat, a["league_pct"]) - a["mean"]) / a["std"]
    val = _num(player.get(CAT_COLUMN[cat]))
    if cat in NEGATIVE_CATS:
        return (a["mean"] - val) / a["std"]      # inverted: fewer is better
    return (val - a["mean"]) / a["std"]


def compute_values(players: list[dict], punt=None) -> list[dict]:
    """Z-score every player across the 9 cats and rank by total value.

    `punt` is a set of category keys to exclude from the total (re-ranking for
    that punt build). Returns dicts sorted by total_value desc with a `rank`.
    """
    punt = set(punt or [])
    avgs = league_averages(players)

    results = []
    for p in players:
        zscores = {cat: round(_zscore(p, cat, avgs), 3) for cat in CATS}
        total = sum(z for cat, z in zscores.items() if cat not in punt)
        results.append({
            "player_id": p.get("player_id"),
            "full_name": p.get("full_name", ""),
            "nba_position": p.get("nba_position"),
            "team": p.get("team"),
            "gp": p.get("gp", 0),
            "mpg": p.get("mpg", 0),
            "zscores": zscores,
            "total_value": round(total, 3),
        })

    results.sort(key=lambda r: r["total_value"], reverse=True)
    for i, r in enumerate(results, 1):
        r["rank"] = i
    return results


# View columns the valuation needs (pulled by rank_from_db).
_VIEW_COLUMNS = [
    "player_id", "full_name", "nba_position", "team", "gp", "mpg",
    "ppg", "rpg", "apg", "spg", "bpg", "topg", "tpm_pg",
    "fg_pct", "ft_pct", "fga_pg", "fta_pg",
    "fgm_tot", "fga_tot", "ftm_tot", "fta_tot",
]


def rank_from_db(
    con,
    *,
    season: str | None = None,
    season_type: str = "Regular Season",
    source: str = "season",
    min_gp: int = 20,
    min_min: float = 10.0,
    punt=None,
) -> list[dict]:
    """Load the qualifying player pool from the views and rank it.

    season=None defaults to the latest season in the data lake, so offseason
    prep needs no year specified. source='season' -> player_season_stats
    (full-season value); source='recent' -> player_recent_form (last 15).
    """
    if season is None:
        from fbball import db as _db
        season = _db.latest_season(con)
    cols = ", ".join(_VIEW_COLUMNS)
    if source == "recent":
        rows = con.execute(
            f"SELECT {cols} FROM player_recent_form WHERE gp_window >= ? AND mpg >= ?",
            [min_gp, min_min],
        ).df().to_dict("records")
    else:
        rows = con.execute(
            f"SELECT {cols} FROM player_season_stats "
            "WHERE season = ? AND season_type = ? AND gp >= ? AND mpg >= ?",
            [season, season_type, min_gp, min_min],
        ).df().to_dict("records")
    return compute_values(rows, punt=punt)
