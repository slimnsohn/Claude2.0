"""Immutable raw JSON archive.

Path scheme:
- Odds:    {root}/{sport}/{YYYY-MM-DD}/{event_id}__{YYYYMMDDTHHMMSSZ}.json
- Results: {root}/{sport}/{game_id_sanitized}.json

`game_id` contains characters illegal on Windows (':' and '@'), so we sanitize
them with a consistent scheme; both write_results and results_archive_exists
use the same helper (_sanitize_game_id):
    ':'  ->  '_'
    '@'  ->  '_at_'

Example: "NBA:20250115:BOS@LAL" -> "NBA_20250115_BOS_at_LAL"
"""
import json
from datetime import datetime
from pathlib import Path


def _sanitize_game_id(game_id: str) -> str:
    """Make a canonical game_id safe for a filename on all platforms."""
    return game_id.replace(":", "_").replace("@", "_at_")


def _odds_path(root: str, sport: str, event_id: str, snapshot_time: datetime) -> Path:
    date_dir = snapshot_time.strftime("%Y-%m-%d")
    fname = f"{event_id}__{snapshot_time.strftime('%Y%m%dT%H%M%SZ')}.json"
    return Path(root) / sport / date_dir / fname


def write_odds(
    *,
    root: str,
    sport: str,
    event_id: str,
    snapshot_time: datetime,
    payload: dict | list,
) -> str:
    """Write odds payload to the archive and return the absolute path."""
    p = _odds_path(root, sport, event_id, snapshot_time)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return str(p)


def odds_archive_exists(
    *,
    root: str,
    sport: str,
    event_id: str,
    snapshot_time: datetime,
) -> bool:
    """Return True if an odds snapshot for this event+time already exists."""
    return _odds_path(root, sport, event_id, snapshot_time).exists()


def _results_path(root: str, sport: str, game_id: str) -> Path:
    return Path(root) / sport / f"{_sanitize_game_id(game_id)}.json"


def write_results(*, root: str, sport: str, game_id: str, payload: dict) -> str:
    """Write results payload to the archive and return the absolute path."""
    p = _results_path(root, sport, game_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return str(p)


def results_archive_exists(*, root: str, sport: str, game_id: str) -> bool:
    """Return True if results for this game_id already exist in the archive."""
    return _results_path(root, sport, game_id).exists()
