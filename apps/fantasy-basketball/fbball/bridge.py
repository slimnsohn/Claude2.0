"""Bridge Yahoo roster players to NBA player_ids — the join the whole
decoupled design hinges on.

Strategy (confidence-first; never guess):
  1. Normalize names (strip accents, punctuation, Jr./Sr. suffixes).
  2. Exact normalized match.
  3. On collision (same normalized name — usually a retired father + active
     son), prefer the active player, then a team match.
  4. Anything still ambiguous or unmatched stays NULL and is surfaced, never
     forced to a wrong join.

An optional alias map handles nicknames (e.g. "Bones Hyland" ->
"Nah'Shon Hyland") that no normalization could reconcile.
"""

import re
import unicodedata

_SUFFIX_RE = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b")
_WS_RE = re.compile(r"\s+")

# Yahoo abbreviations that differ from nba_api's, for team disambiguation.
_YAHOO_TEAM_FIX = {
    "GS": "GSW", "NO": "NOP", "NY": "NYK", "SA": "SAS",
    "PHO": "PHX", "WAS": "WAS", "UTAH": "UTA",
}


def normalize_name(name: str) -> str:
    """Lowercase, strip accents, drop '.'/apostrophes and Jr./Sr. suffixes."""
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    s = s.lower().replace(".", "").replace("'", "")
    s = _SUFFIX_RE.sub("", s)
    return _WS_RE.sub(" ", s).strip()


def _team_key(abbr: str) -> str:
    a = (abbr or "").upper()
    return _YAHOO_TEAM_FIX.get(a, a)


def _resolve(candidates: list, yahoo_team: str):
    """Pick one player_id from same-normalized-name candidates, or None.

    candidates: list of (player_id, is_active, team).
    """
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0][0]

    # Prefer active players.
    active = [c for c in candidates if c[1]]
    if len(active) == 1:
        return active[0][0]

    # Still ambiguous → require a team match.
    pool = active or candidates
    yk = _team_key(yahoo_team)
    team_hits = [c for c in pool if yk and _team_key(c[2]) == yk]
    if len(team_hits) == 1:
        return team_hits[0][0]

    return None  # genuinely ambiguous — surface rather than guess


def match_rosters(roster_rows: list, nba_rows: list, aliases: dict | None = None) -> list:
    """Map each roster row to an nba_player_id (or None).

    roster_rows: dicts with player_key, player_name, editorial_team.
    nba_rows:    dicts with player_id, full_name, is_active, team.
    aliases:     {yahoo_name -> nba_name} for nicknames.
    """
    alias_norm = {normalize_name(k): normalize_name(v) for k, v in (aliases or {}).items()}

    index = {}
    for r in nba_rows:
        index.setdefault(normalize_name(r["full_name"]), []).append(
            (r["player_id"], bool(r.get("is_active")), r.get("team"))
        )

    out = []
    for row in roster_rows:
        key = normalize_name(row["player_name"])
        key = alias_norm.get(key, key)
        pid = _resolve(index.get(key, []), row.get("editorial_team", ""))
        out.append({"player_key": row["player_key"], "nba_player_id": pid})
    return out
