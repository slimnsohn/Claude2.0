"""Projection engine — project next-season per-game stats from recent history.

Modernized from the old project's projections.py:
  - Age handled as a GROWTH/DECLINE RATIO (curve(target)/curve(recent)), so
    young players on the rising part project up and veterans decline — the old
    model multiplied by curve(age) directly, which wrongly deflated youngsters.
  - Each season is SAMPLE-WEIGHTED by games played, so a small hot sample can't
    dominate a full prior season.
  - Recency-weighted blend of the last few seasons.

Output rows match the player_season_stats shape, so they feed valuation /
draft / waivers unchanged (just `source='projection'`).
"""

# Fraction-of-peak production by age (peak 25-27). Used only as a ratio.
AGE_CURVE = {
    19: 0.85, 20: 0.88, 21: 0.91, 22: 0.94, 23: 0.97, 24: 0.99,
    25: 1.00, 26: 1.00, 27: 1.00, 28: 0.99, 29: 0.98, 30: 0.97,
    31: 0.95, 32: 0.93, 33: 0.91, 34: 0.88, 35: 0.85, 36: 0.82,
    37: 0.79, 38: 0.76, 39: 0.73, 40: 0.70,
}
RECENCY_WEIGHTS = [0.5, 0.3, 0.2]   # most recent season first
GP_CAP = 65                          # games for a "full" sample-weight of 1.0
MAX_SEASONS = 3

_COUNTING = ["ppg", "rpg", "apg", "spg", "bpg", "topg", "tpm_pg",
             "fgm_pg", "fga_pg", "ftm_pg", "fta_pg"]


def age_curve(age: float) -> float:
    a = int(round(age))
    if a < 19:
        a = 19
    elif a > 40:
        a = 40
    return AGE_CURVE[a]


def _num(x):
    if x is None:
        return 0.0
    x = float(x)
    return 0.0 if x != x else x


def project_player(season_rows: list[dict], target_age, target_season: str) -> dict:
    """Project one player's per-game line for target_season from recent seasons."""
    target_start = int(target_season[:4])
    rows = sorted(season_rows, key=lambda r: r["season"], reverse=True)[:MAX_SEASONS]

    # weight = recency * sample(gp)
    weights, ages = [], []
    for i, r in enumerate(rows):
        recency = RECENCY_WEIGHTS[i] if i < len(RECENCY_WEIGHTS) else RECENCY_WEIGHTS[-1]
        sample = min(_num(r.get("gp")), GP_CAP) / GP_CAP
        weights.append(recency * sample)
        ages.append(target_age - (target_start - int(r["season"][:4])))
    total_w = sum(weights) or 1.0

    def wavg(key):
        return sum(w * _num(r.get(key)) for w, r in zip(weights, rows)) / total_w

    ref_age = sum(w * a for w, a in zip(weights, ages)) / total_w
    age_factor = age_curve(target_age) / age_curve(ref_age)

    proj = {k: wavg(k) * age_factor for k in _COUNTING}
    proj["mpg"] = wavg("mpg")
    proj_gp = wavg("gp")
    proj["gp"] = proj_gp

    # percentages from projected makes/attempts (age cancels in the ratio)
    proj["fg_pct"] = proj["fgm_pg"] / proj["fga_pg"] if proj["fga_pg"] > 0 else 0.0
    proj["ft_pct"] = proj["ftm_pg"] / proj["fta_pg"] if proj["fta_pg"] > 0 else 0.0

    # totals (valuation's impact method needs them)
    proj["fgm_tot"] = proj["fgm_pg"] * proj_gp
    proj["fga_tot"] = proj["fga_pg"] * proj_gp
    proj["ftm_tot"] = proj["ftm_pg"] * proj_gp
    proj["fta_tot"] = proj["fta_pg"] * proj_gp
    return proj


def project_players(con, target_season: str | None = None, *,
                    min_seasons: int = 1, min_recent_gp: int = 20) -> list[dict]:
    """Project every eligible player for target_season (default: the season
    after the latest in the lake). Returns player_season_stats-shaped rows."""
    from fbball import db

    latest = db.latest_season(con)
    if latest is None:
        return []
    if target_season is None:
        target_season = f"{int(latest[:4]) + 1}-{str(int(latest[:4]) + 2)[-2:]}"

    ages = db.ages_for_target(con, target_season)
    rows = con.execute(
        """
        SELECT player_id, full_name, nba_position, team, season, gp, mpg,
               ppg, rpg, apg, spg, bpg, topg, tpm_pg,
               fgm_pg, fga_pg, ftm_pg, fta_pg
        FROM player_season_stats
        WHERE season_type = 'Regular Season' AND season < ?
        """,
        [target_season],
    ).df().to_dict("records")

    by_player = {}
    for r in rows:
        by_player.setdefault(r["player_id"], []).append(r)

    out = []
    for pid, seasons in by_player.items():
        if len(seasons) < min_seasons:
            continue
        recent = max(seasons, key=lambda r: r["season"])
        if _num(recent.get("gp")) < min_recent_gp:
            continue
        target_age = ages.get(pid, 26)   # unknown age -> neutral (peak)
        p = project_player(seasons, target_age, target_season)
        p.update({
            "player_id": pid,
            "full_name": recent.get("full_name", ""),
            "nba_position": recent.get("nba_position"),
            "team": recent.get("team"),
        })
        out.append(p)
    return out
