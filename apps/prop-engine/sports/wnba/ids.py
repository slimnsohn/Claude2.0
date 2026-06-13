"""Player ID crosswalk: The Odds API uses display names; stats.wnba.com uses
integer player_ids. This module normalizes names and fuzzy-matches them to
stats.wnba.com rosters with a manual override file for known edge cases."""
from __future__ import annotations
import json
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

_MANUAL = Path(__file__).with_name("manual_id_overrides.json")


def normalize_name(name: str) -> str:
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().replace("'", "").replace(".", "").replace("-", " ")
    return " ".join(s.split())


def fuzzy_match_player(name: str, roster: list[dict], threshold: float = 0.85) -> dict | None:
    overrides = json.loads(_MANUAL.read_text()) if _MANUAL.exists() else {}
    norm = normalize_name(name)
    if norm in overrides:
        target_id = overrides[norm]
        for r in roster:
            if str(r.get("player_id")) == str(target_id):
                return r

    best, best_score = None, 0.0
    for r in roster:
        score = SequenceMatcher(None, norm, normalize_name(r["full_name"])).ratio()
        if score > best_score:
            best, best_score = r, score
    return best if best_score >= threshold else None
