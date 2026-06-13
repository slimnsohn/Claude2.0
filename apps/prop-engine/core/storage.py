"""SQLite persistence layer for the prop engine."""
from __future__ import annotations
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Silence Py3.12+ deprecation: register explicit adapters for datetime
sqlite3.register_adapter(datetime, lambda dt: dt.isoformat(sep=" "))


SCHEMA = """
CREATE TABLE IF NOT EXISTS sports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sport_id TEXT UNIQUE NOT NULL
);
CREATE TABLE IF NOT EXISTS markets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sport_id INTEGER NOT NULL,
    event_id TEXT NOT NULL,
    commence_time TIMESTAMP NOT NULL,
    market_type TEXT NOT NULL,
    player_name TEXT NOT NULL,
    player_external_ids TEXT,
    line_value REAL NOT NULL,
    side TEXT NOT NULL,
    is_alternate INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (event_id, market_type, player_name, line_value, side),
    FOREIGN KEY (sport_id) REFERENCES sports(id)
);
CREATE INDEX IF NOT EXISTS idx_markets_event ON markets(event_id);

CREATE TABLE IF NOT EXISTS book_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id INTEGER NOT NULL,
    book TEXT NOT NULL,
    american_odds INTEGER NOT NULL,
    fetched_at TIMESTAMP NOT NULL,
    FOREIGN KEY (market_id) REFERENCES markets(id)
);
CREATE INDEX IF NOT EXISTS idx_book_lines_market_time ON book_lines(market_id, fetched_at DESC);

CREATE TABLE IF NOT EXISTS projections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id INTEGER NOT NULL,
    run_id INTEGER NOT NULL,
    sigma_used REAL NOT NULL,
    consensus_prob REAL NOT NULL,
    mu_implied REAL NOT NULL,
    mu_adjusted REAL NOT NULL,
    posterior_prob REAL NOT NULL,
    residual_breakdown TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (market_id) REFERENCES markets(id),
    FOREIGN KEY (run_id) REFERENCES runs(id)
);

CREATE TABLE IF NOT EXISTS plays (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    projection_id INTEGER NOT NULL,
    book TEXT NOT NULL,
    offered_odds INTEGER NOT NULL,
    edge_pct REAL NOT NULL,
    recommended_stake REAL NOT NULL,
    ev_dollars REAL NOT NULL,
    status TEXT DEFAULT 'open',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (projection_id) REFERENCES projections(id)
);

CREATE TABLE IF NOT EXISTS bets_placed (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    play_id INTEGER,
    stake_actual REAL NOT NULL,
    odds_actual INTEGER NOT NULL,
    book TEXT NOT NULL,
    placed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    settled INTEGER DEFAULT 0,
    result TEXT,
    profit REAL,
    settled_at TIMESTAMP,
    notes TEXT,
    FOREIGN KEY (play_id) REFERENCES plays(id)
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sport_id INTEGER NOT NULL,
    started_at TIMESTAMP NOT NULL,
    finished_at TIMESTAMP,
    status TEXT NOT NULL,
    n_markets INTEGER,
    n_plays INTEGER,
    log TEXT,
    FOREIGN KEY (sport_id) REFERENCES sports(id)
);

CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class StorageBackend:
    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.db_path)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys = ON")
        return c

    def initialize(self) -> None:
        with self._conn() as c:
            c.executescript(SCHEMA)

    def list_tables(self) -> list[str]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            return [r["name"] for r in rows]

    # ---- sports ----
    def upsert_sport(self, sport_id: str) -> int:
        with self._conn() as c:
            c.execute("INSERT OR IGNORE INTO sports (sport_id) VALUES (?)", (sport_id,))
            row = c.execute("SELECT id FROM sports WHERE sport_id = ?", (sport_id,)).fetchone()
            return row["id"]

    # ---- markets ----
    def upsert_market(
        self, sport_id: int, event_id: str, market_type: str,
        player_name: str, line_value: float, side: str,
        commence_time: datetime, is_alternate: bool = False,
        player_external_ids: Optional[dict] = None,
    ) -> int:
        with self._conn() as c:
            c.execute(
                """INSERT OR IGNORE INTO markets
                   (sport_id, event_id, commence_time, market_type, player_name,
                    player_external_ids, line_value, side, is_alternate)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (sport_id, event_id, commence_time, market_type, player_name,
                 json.dumps(player_external_ids or {}), line_value, side,
                 1 if is_alternate else 0),
            )
            row = c.execute(
                """SELECT id FROM markets WHERE event_id=? AND market_type=?
                   AND player_name=? AND line_value=? AND side=?""",
                (event_id, market_type, player_name, line_value, side),
            ).fetchone()
            return row["id"]

    # ---- book lines ----
    def record_book_line(self, market_id: int, book: str, american_odds: int,
                          fetched_at: datetime) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO book_lines (market_id, book, american_odds, fetched_at) "
                "VALUES (?, ?, ?, ?)",
                (market_id, book, american_odds, fetched_at),
            )

    def latest_book_lines(self, market_id: int) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                """SELECT bl.* FROM book_lines bl
                   WHERE bl.market_id = ?
                   AND bl.fetched_at = (
                       SELECT MAX(fetched_at) FROM book_lines
                       WHERE market_id = bl.market_id AND book = bl.book
                   )""",
                (market_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    # ---- runs ----
    def start_run(self, sport_id: int) -> int:
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO runs (sport_id, started_at, status, log) "
                "VALUES (?, ?, 'running', '')",
                (sport_id, datetime.now(timezone.utc).replace(tzinfo=None)),
            )
            return cur.lastrowid

    def append_run_log(self, run_id: int, line: str) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE runs SET log = COALESCE(log,'') || ? WHERE id = ?",
                (line + "\n", run_id),
            )

    def finish_run(self, run_id: int, status: str, n_markets: int = 0,
                    n_plays: int = 0) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE runs SET finished_at = ?, status = ?, n_markets = ?, n_plays = ? "
                "WHERE id = ?",
                (datetime.now(timezone.utc).replace(tzinfo=None), status, n_markets, n_plays, run_id),
            )

    def get_run(self, run_id: int) -> dict:
        with self._conn() as c:
            row = c.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
            return dict(row) if row else {}

    # ---- projections + plays ----
    def record_projection(self, market_id: int, run_id: int, sigma_used: float,
                           consensus_prob: float, mu_implied: float,
                           mu_adjusted: float, posterior_prob: float,
                           residual_breakdown: dict, notes: list) -> int:
        with self._conn() as c:
            cur = c.execute(
                """INSERT INTO projections (market_id, run_id, sigma_used, consensus_prob,
                       mu_implied, mu_adjusted, posterior_prob, residual_breakdown, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (market_id, run_id, sigma_used, consensus_prob, mu_implied,
                 mu_adjusted, posterior_prob, json.dumps(residual_breakdown),
                 json.dumps(notes)),
            )
            return cur.lastrowid

    def record_play(self, projection_id: int, book: str, offered_odds: int,
                     edge_pct: float, recommended_stake: float,
                     ev_dollars: float) -> int:
        with self._conn() as c:
            cur = c.execute(
                """INSERT INTO plays (projection_id, book, offered_odds, edge_pct,
                       recommended_stake, ev_dollars)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (projection_id, book, offered_odds, edge_pct, recommended_stake,
                 ev_dollars),
            )
            return cur.lastrowid

    def open_plays(self) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                """SELECT p.id, p.projection_id, p.book, p.offered_odds, p.edge_pct,
                          p.recommended_stake, p.ev_dollars, p.status, p.created_at,
                          pr.posterior_prob, pr.consensus_prob, pr.mu_adjusted,
                          pr.residual_breakdown, pr.notes,
                          m.player_name, m.market_type, m.line_value, m.side,
                          m.commence_time, m.event_id
                   FROM plays p
                   JOIN projections pr ON pr.id = p.projection_id
                   JOIN markets m ON m.id = pr.market_id
                   WHERE p.status = 'open'
                   ORDER BY p.edge_pct DESC"""
            ).fetchall()
            return [dict(r) for r in rows]

    # ---- bets ----
    def log_bet(self, play_id: int, stake_actual: float, odds_actual: int,
                 book: str, notes: str = "") -> int:
        with self._conn() as c:
            cur = c.execute(
                """INSERT INTO bets_placed (play_id, stake_actual, odds_actual, book, notes)
                   VALUES (?, ?, ?, ?, ?)""",
                (play_id, stake_actual, odds_actual, book, notes),
            )
            c.execute("UPDATE plays SET status = 'logged' WHERE id = ?", (play_id,))
            return cur.lastrowid

    def settle_bet(self, bet_id: int, result: str, profit: float) -> None:
        with self._conn() as c:
            c.execute(
                """UPDATE bets_placed SET settled = 1, result = ?, profit = ?,
                       settled_at = ? WHERE id = ?""",
                (result, profit, datetime.now(timezone.utc).replace(tzinfo=None), bet_id),
            )

    def all_bets(self) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM bets_placed ORDER BY placed_at DESC").fetchall()
            return [dict(r) for r in rows]

    # ---- config ----
    def set_config(self, key: str, value: str) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO config (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def get_config(self, key: str) -> Optional[str]:
        with self._conn() as c:
            row = c.execute("SELECT value FROM config WHERE key = ?", (key,)).fetchone()
            return row["value"] if row else None
