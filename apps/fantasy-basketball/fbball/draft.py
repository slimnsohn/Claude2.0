"""Draft board — punt-aware value rankings, grouped into tiers, with
positional rank for scarcity.

Tiers come from value gaps: walking the ranked list, a new tier starts wherever
the drop in total value from the previous player exceeds `gap`. That captures
the natural cliffs draft strategy cares about ("grab one before this tier dries
up") better than fixed-size buckets.
"""

from fbball import valuation


def assign_tiers(ranked: list[dict], gap: float = 0.75) -> list[dict]:
    """Add a `tier` to each player (ranked desc by total_value).

    Tier 1 is the best; a new tier begins when value drops by more than `gap`
    from the previous player.
    """
    out = []
    tier = 1
    prev = None
    for p in ranked:
        if prev is not None and (prev - p["total_value"]) > gap:
            tier += 1
        r = dict(p)
        r["tier"] = tier
        out.append(r)
        prev = p["total_value"]
    return out


def primary_position(pos) -> str:
    """Primary NBA position for scarcity grouping: 'F-C' -> 'F', None -> 'NA'."""
    if not pos:
        return "NA"
    return pos.split("-")[0] or "NA"


def positional_ranks(ranked: list[dict]) -> list[dict]:
    """Add `pos_rank` (e.g. 'C3' = 3rd-best center) — value rank within a
    player's PRIMARY position. Unknown positions are grouped under 'NA'."""
    seen = {}
    out = []
    for p in ranked:
        pos = primary_position(p.get("nba_position"))
        seen[pos] = seen.get(pos, 0) + 1
        r = dict(p)
        r["pos_rank"] = f"{pos}{seen[pos]}"
        out.append(r)
    return out


def build_board(
    con,
    *,
    season: str | None = None,
    season_type: str = "Regular Season",
    source: str = "season",
    min_gp: int = 20,
    min_min: float = 10.0,
    punt=None,
    gap: float = 0.75,
) -> list[dict]:
    """Full draft board: value (punt-aware) -> tiers -> positional ranks."""
    ranked = valuation.rank_from_db(
        con, season=season, season_type=season_type, source=source,
        min_gp=min_gp, min_min=min_min, punt=punt,
    )
    return positional_ranks(assign_tiers(ranked, gap=gap))
