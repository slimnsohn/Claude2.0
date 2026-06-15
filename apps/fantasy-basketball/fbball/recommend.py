"""Waiver recommendations — rank free agents by MARGINAL value to my roster's
category needs, not raw value.

The principle (from the build spec): a player who helps the cats I'm weak in
outranks a higher-raw-value player who piles onto a cat I'm already winning.

Mechanics:
  1. category_profile  — my roster's total z-score in each cat (my strengths).
  2. needs_weights     — weakest cat -> weight 1, strongest -> 0 (punts -> 0).
  3. score_for_needs   — a free agent's z-scores dotted with those weights.
"""

from fbball import valuation
from fbball.valuation import CATS


def category_profile(players: list[dict]) -> dict:
    """Sum each cat's z-score across a set of valued players."""
    return {cat: sum(p["zscores"].get(cat, 0.0) for p in players) for cat in CATS}


def needs_weights(profile: dict, punt=None) -> dict:
    """Per-cat weight in [0,1]: weakest cat highest, strongest lowest.

    Punted cats get weight 0 and don't influence the spread. A flat profile
    (no spread) weights every cat equally at 1.0.
    """
    punt = set(punt or [])
    active = [c for c in CATS if c not in punt]
    vals = [profile.get(c, 0.0) for c in active]
    lo, hi = (min(vals), max(vals)) if vals else (0.0, 0.0)

    weights = {}
    for cat in CATS:
        if cat in punt:
            weights[cat] = 0.0
        elif hi == lo:
            weights[cat] = 1.0
        else:
            weights[cat] = (hi - profile.get(cat, 0.0)) / (hi - lo)
    return weights


def score_for_needs(player: dict, weights: dict) -> float:
    """A player's z-scores weighted by how much I need each category."""
    return sum(player["zscores"].get(cat, 0.0) * weights[cat] for cat in CATS)


def rank_waivers(candidates: list[dict], weights: dict) -> list[dict]:
    """Rank free agents by needs-weighted value. Returns copies with a
    `needs_value` and `rank`, sorted desc."""
    scored = []
    for c in candidates:
        out = dict(c)
        out["needs_value"] = round(score_for_needs(c, weights), 3)
        scored.append(out)
    scored.sort(key=lambda r: r["needs_value"], reverse=True)
    for i, r in enumerate(scored, 1):
        r["rank"] = i
    return scored


def recommend_waivers(
    con,
    *,
    season: str | None = None,
    source: str = "season",
    min_gp: int = 20,
    min_min: float = 10.0,
    punt=None,
    top: int = 15,
) -> dict:
    """Rank a league's bridged free agents by marginal value to my roster.

    Values everyone against the same qualifying pool, reads my roster's
    category profile, then scores free agents by how well they fill my needs.
    """
    ranked = valuation.rank_from_db(
        con, season=season, source=source, min_gp=min_gp, min_min=min_min, punt=punt
    )
    by_pid = {r["player_id"]: r for r in ranked}

    my_ids = [
        row[0] for row in con.execute(
            "SELECT r.nba_player_id FROM yahoo_roster r JOIN yahoo_teams t USING (team_key) "
            "WHERE t.is_my_team AND r.nba_player_id IS NOT NULL"
        ).fetchall()
    ]
    profile = category_profile([by_pid[i] for i in my_ids if i in by_pid])
    weights = needs_weights(profile, punt)

    fa_rows = con.execute(
        "SELECT nba_player_id, player_name, editorial_team, eligible_positions, status "
        "FROM yahoo_free_agents WHERE nba_player_id IS NOT NULL"
    ).fetchall()
    candidates = []
    for pid, yname, team, elig, status in fa_rows:
        if pid in by_pid:
            c = dict(by_pid[pid])
            c["eligible_positions"] = elig
            c["status"] = status or ""
            candidates.append(c)

    recs = rank_waivers(candidates, weights)
    return {
        "profile": profile,
        "weights": weights,
        "pool": len(candidates),
        "recommendations": recs[:top],
    }
