"""Build derived SQLite tables from raw JSON archive."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from dateutil import parser as dtparser

from odds_pipeline.identity import matcher
from odds_pipeline.store import migrate

MARKET_SEGMENT_MAP = {
    "h2h": "FULL", "spreads": "FULL", "totals": "FULL",
    "h2h_q1": "Q1", "spreads_q1": "Q1", "totals_q1": "Q1",
    "h2h_q2": "Q2", "spreads_q2": "Q2", "totals_q2": "Q2",
    "h2h_q3": "Q3", "spreads_q3": "Q3", "totals_q3": "Q3",
    "h2h_q4": "Q4", "spreads_q4": "Q4", "totals_q4": "Q4",
    "h2h_h1": "H1", "spreads_h1": "H1", "totals_h1": "H1",
    "h2h_h2": "H2", "spreads_h2": "H2", "totals_h2": "H2",
    "spreads_p1": "P1", "totals_p1": "P1",
    "spreads_p2": "P2", "totals_p2": "P2",
    "spreads_p3": "P3", "totals_p3": "P3",
    "spreads_1st_5_innings": "F5", "totals_1st_5_innings": "F5",
}


def _market_type_for(market_key: str) -> str:
    if market_key.startswith("h2h"):
        return "h2h"
    if market_key.startswith("spreads"):
        return "spreads"
    if market_key.startswith("totals"):
        return "totals"
    return market_key


def _outcome_side(market_type: str, name: str, home: str, away: str) -> str:
    if market_type == "totals":
        return "over" if name.lower() == "over" else "under"
    return "home" if name == home else "away"


def _american_to_decimal(american: int) -> float:
    if american >= 100:
        return 1 + american / 100
    return 1 + 100 / abs(american)


def _clear_derived(conn):
    # build_all() disables FKs for the duration of derive, so this order is not
    # strictly required today. Kept child-tables-first as a safeguard if a caller
    # ever invokes this function with FKs enabled. Note: executescript() commits
    # implicitly, so this is not atomic with the ingest that follows — a crash
    # mid-derive leaves an empty DB until the next successful rebuild.
    conn.executescript(
        "DELETE FROM odds_snapshots; DELETE FROM scores; DELETE FROM games;"
    )


def _ingest_odds_file(conn, sport: str, path: Path):
    data = json.loads(path.read_text())
    meta = data["_meta"]
    payload = data["payload"]
    snapshot_time = meta["snapshot_time"]

    # The historical-event-odds endpoint returns {timestamp, previous_timestamp,
    # next_timestamp, data: {event...}}. Unwrap `data` to reach the event. Some
    # older or test-shape archives may already be unwrapped — accept both.
    event = payload["data"] if isinstance(payload, dict) and "data" in payload and "commence_time" not in payload else payload

    commence = dtparser.isoparse(event["commence_time"])

    home_raw = event["home_team"]
    away_raw = event["away_team"]
    home = matcher.canonical_team(sport, home_raw)
    away = matcher.canonical_team(sport, away_raw)
    game_id = matcher.build_game_id(sport, commence, home, away)

    now = datetime.now(tz=timezone.utc).isoformat()
    conn.execute(
        "INSERT OR IGNORE INTO games (game_id, sport, commence_time, home_team, away_team, "
        "odds_api_event_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (game_id, sport, commence.isoformat(), home, away,
         event.get("id"), now, now),
    )

    rel_path = str(path)
    for bm in event.get("bookmakers", []):
        book_key = bm["key"]
        for market in bm.get("markets", []):
            mkey = market["key"]
            mtype = _market_type_for(mkey)
            segment = MARKET_SEGMENT_MAP.get(mkey, "FULL")
            for outcome in market.get("outcomes", []):
                side = _outcome_side(mtype, outcome["name"], event["home_team"], event["away_team"])
                line = outcome.get("point")
                price = int(outcome["price"])
                conn.execute(
                    "INSERT INTO odds_snapshots (game_id, bookmaker_key, segment_key, market_type, "
                    "side, line, price_american, price_decimal, snapshot_time, is_close, raw_archive_path) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)",
                    (game_id, book_key, segment, mtype, side, line,
                     price, _american_to_decimal(price), snapshot_time, rel_path),
                )


def _ingest_results_file(conn, sport: str, path: Path):
    data = json.loads(path.read_text())
    game_id = data["game_id"]
    commence = dtparser.isoparse(data["commence_time"])
    home = data["home_team_canonical"]
    away = data["away_team_canonical"]
    now = datetime.now(tz=timezone.utc).isoformat()
    conn.execute(
        "INSERT OR IGNORE INTO games (game_id, sport, commence_time, home_team, away_team, "
        "results_source_game_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (game_id, sport, commence.isoformat(), home, away,
         data.get("source_game_id"), now, now),
    )
    conn.execute(
        "UPDATE games SET results_source_game_id=COALESCE(results_source_game_id, ?), "
        "updated_at=? WHERE game_id=?",
        (data.get("source_game_id"), now, game_id),
    )
    rel_path = str(path)
    for seg, score_pair in data["segment_scores"].items():
        # Results adapters return segment_scores values as a 2-tuple (h, a), but
        # JSON round-trip turns those into lists. Accept either; reject anything
        # else with a clear error rather than silently corrupting the row.
        if not (isinstance(score_pair, (list, tuple)) and len(score_pair) == 2):
            raise ValueError(
                f"Bad segment_scores shape in {path} for segment {seg!r}: expected [home, away], got {score_pair!r}"
            )
        h_score, a_score = score_pair
        conn.execute(
            "INSERT OR REPLACE INTO scores (game_id, segment_key, home_score, away_score, raw_archive_path) "
            "VALUES (?, ?, ?, ?, ?)",
            (game_id, seg, int(h_score), int(a_score), rel_path),
        )


def build_all(*, db_path: str, odds_root: str, results_root: str):
    conn = migrate.connect(db_path)
    # FK enforcement is on by default from connect(); we turn it OFF for derive
    # because results may arrive before odds for the same game_id during partial pulls.
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        _clear_derived(conn)
        odds_path = Path(odds_root)
        if odds_path.exists():
            for sport_dir in odds_path.iterdir():
                if not sport_dir.is_dir():
                    continue
                sport = sport_dir.name
                for f in sport_dir.rglob("*.json"):
                    _ingest_odds_file(conn, sport, f)
        results_path = Path(results_root)
        if results_path.exists():
            for sport_dir in results_path.iterdir():
                if not sport_dir.is_dir():
                    continue
                sport = sport_dir.name
                for f in sport_dir.glob("*.json"):
                    _ingest_results_file(conn, sport, f)
        conn.commit()
    finally:
        conn.close()
