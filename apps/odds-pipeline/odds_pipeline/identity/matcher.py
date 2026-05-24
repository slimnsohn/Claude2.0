"""Cross-source identity matching: team name canonicalization and game matching."""
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

ALIASES_DIR = Path(__file__).parent / "aliases"

_alias_cache: dict[str, dict[str, str]] = {}


def _load_aliases(sport: str) -> dict[str, str]:
    if sport not in _alias_cache:
        path = ALIASES_DIR / f"{sport}.json"
        _alias_cache[sport] = json.loads(path.read_text()) if path.exists() else {}
    return _alias_cache[sport]


def canonical_team(sport: str, raw_name: str) -> str:
    """Look up raw_name in identity/aliases/{sport}.json; return canonical or upper-cased raw."""
    aliases = _load_aliases(sport)
    if raw_name in aliases:
        return aliases[raw_name]
    return raw_name.upper()


def build_game_id(sport: str, commence_time: datetime, home: str, away: str) -> str:
    """'{sport}:{yyyymmdd}:{away}@{home}'."""
    return f"{sport}:{commence_time.strftime('%Y%m%d')}:{away}@{home}"


@dataclass
class OddsEvent:
    sport: str
    commence_time: datetime
    home_team_raw: str
    away_team_raw: str
    event_id: str


@dataclass
class ResultCandidate:
    sport: str
    commence_time: datetime
    home_team_canonical: str
    away_team_canonical: str
    source_game_id: str


def match_game(odds: OddsEvent, candidates: list[ResultCandidate]) -> ResultCandidate | None:
    """Match odds event to a results candidate. Date tolerance: ±1 day (TZ slop)."""
    odds_home = canonical_team(odds.sport, odds.home_team_raw)
    odds_away = canonical_team(odds.sport, odds.away_team_raw)
    for c in candidates:
        if c.sport != odds.sport:
            continue
        if abs((c.commence_time - odds.commence_time).total_seconds()) > 86400:
            continue
        if c.home_team_canonical == odds_home and c.away_team_canonical == odds_away:
            return c
    return None
