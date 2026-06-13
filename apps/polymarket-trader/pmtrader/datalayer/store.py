"""SQLite event store. Single writer connection, WAL mode, thread-safe via lock.

Async code must call through asyncio.to_thread; the lock keeps cross-thread
access safe. All payloads JSON-serialized; all queries parameterized.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Optional

from pmtrader.core.models import Fill, Intent, Market, Order

SCHEMA = """
CREATE TABLE IF NOT EXISTS markets (
    condition_id TEXT PRIMARY KEY,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS resolutions (
    condition_id TEXT PRIMARY KEY,
    winning_token_id TEXT NOT NULL,
    resolved_ts REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS price_history (
    token_id TEXT NOT NULL,
    ts REAL NOT NULL,
    price REAL NOT NULL,
    PRIMARY KEY (token_id, ts)
);
CREATE TABLE IF NOT EXISTS intents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    strategy TEXT NOT NULL,
    token_id TEXT NOT NULL,
    side TEXT NOT NULL,
    price REAL NOT NULL,
    size REAL NOT NULL,
    expected_edge REAL NOT NULL,
    reasoning TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY,
    ts REAL NOT NULL,
    status TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT NOT NULL,
    token_id TEXT NOT NULL,
    side TEXT NOT NULL,
    price REAL NOT NULL,
    size REAL NOT NULL,
    fee REAL NOT NULL,
    ts REAL NOT NULL,
    maker INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS equity_snapshots (
    ts REAL PRIMARY KEY,
    equity REAL NOT NULL,
    cash REAL NOT NULL,
    mode TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    strategy TEXT NOT NULL,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS strategy_stats (
    strategy TEXT NOT NULL,
    ts REAL NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (strategy, ts)
);
CREATE TABLE IF NOT EXISTS fetch_checkpoints (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fills_token ON fills(token_id);
CREATE INDEX IF NOT EXISTS idx_intents_ts ON intents(ts);
CREATE INDEX IF NOT EXISTS idx_decisions_ts ON decisions(ts);
"""


class Store:
    def __init__(self, path: str | Path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def journal_mode(self) -> str:
        with self._lock:
            return self._conn.execute("PRAGMA journal_mode").fetchone()[0]

    # -- markets ------------------------------------------------------------
    def upsert_market(self, m: Market) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO markets (condition_id, payload) VALUES (?, ?) "
                "ON CONFLICT(condition_id) DO UPDATE SET payload=excluded.payload",
                (m.condition_id, m.model_dump_json()),
            )
            self._conn.commit()

    def get_market(self, condition_id: str) -> Optional[Market]:
        with self._lock:
            row = self._conn.execute(
                "SELECT payload FROM markets WHERE condition_id=?", (condition_id,)
            ).fetchone()
        return Market.model_validate_json(row["payload"]) if row else None

    def all_markets(self) -> list[Market]:
        with self._lock:
            rows = self._conn.execute("SELECT payload FROM markets").fetchall()
        return [Market.model_validate_json(r["payload"]) for r in rows]

    # -- resolutions ---------------------------------------------------------
    def set_resolution(self, condition_id: str, winning_token_id: str, resolved_ts: float) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO resolutions (condition_id, winning_token_id, resolved_ts) "
                "VALUES (?, ?, ?) ON CONFLICT(condition_id) DO UPDATE SET "
                "winning_token_id=excluded.winning_token_id, resolved_ts=excluded.resolved_ts",
                (condition_id, winning_token_id, resolved_ts),
            )
            self._conn.commit()

    def resolutions(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT condition_id, winning_token_id, resolved_ts FROM resolutions"
            ).fetchall()
        return [dict(r) for r in rows]

    # -- price history --------------------------------------------------------
    def insert_price_history(self, token_id: str, points: list[tuple[float, float]]) -> None:
        with self._lock:
            self._conn.executemany(
                "INSERT OR IGNORE INTO price_history (token_id, ts, price) VALUES (?, ?, ?)",
                [(token_id, t, p) for t, p in points],
            )
            self._conn.commit()

    def price_history(self, token_id: str, start_ts: float = 0.0,
                      end_ts: float = float("inf")) -> list[tuple[float, float]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT ts, price FROM price_history WHERE token_id=? AND ts>=? AND ts<=? "
                "ORDER BY ts", (token_id, start_ts, end_ts),
            ).fetchall()
        return [(r["ts"], r["price"]) for r in rows]

    def tokens_with_history(self) -> list[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT DISTINCT token_id FROM price_history").fetchall()
        return [r["token_id"] for r in rows]

    def price_history_span(self) -> tuple[Optional[float], Optional[float]]:
        with self._lock:
            row = self._conn.execute(
                "SELECT MIN(ts) AS lo, MAX(ts) AS hi FROM price_history").fetchone()
        return (row["lo"], row["hi"])

    # -- intents / orders / fills ----------------------------------------------
    def insert_intent(self, i: Intent, ts: float) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO intents (ts, strategy, token_id, side, price, size, "
                "expected_edge, reasoning, payload) VALUES (?,?,?,?,?,?,?,?,?)",
                (ts, i.strategy, i.token_id, i.side.value, i.price, i.size,
                 i.expected_edge, i.reasoning, i.model_dump_json()),
            )
            self._conn.commit()
            return cur.lastrowid

    def intents(self, limit: int = 100) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM intents ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def upsert_order(self, o: Order) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO orders (id, ts, status, payload) VALUES (?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET status=excluded.status, payload=excluded.payload",
                (o.id, o.updated_ts, o.status.value, o.model_dump_json()),
            )
            self._conn.commit()

    def orders_by_status(self, *statuses: str) -> list[Order]:
        marks = ",".join("?" for _ in statuses)
        with self._lock:
            rows = self._conn.execute(
                f"SELECT payload FROM orders WHERE status IN ({marks})", statuses).fetchall()
        return [Order.model_validate_json(r["payload"]) for r in rows]

    def all_orders(self) -> list[Order]:
        with self._lock:
            rows = self._conn.execute("SELECT payload FROM orders").fetchall()
        return [Order.model_validate_json(r["payload"]) for r in rows]

    def insert_fill(self, f: Fill) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO fills (order_id, token_id, side, price, size, fee, ts, maker) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (f.order_id, f.token_id, f.side.value, f.price, f.size, f.fee, f.ts,
                 int(f.maker)),
            )
            self._conn.commit()

    def fills(self, token_id: Optional[str] = None, since_ts: float = 0.0) -> list[dict]:
        q = "SELECT * FROM fills WHERE ts>=?"
        params: list[Any] = [since_ts]
        if token_id is not None:
            q += " AND token_id=?"
            params.append(token_id)
        with self._lock:
            rows = self._conn.execute(q + " ORDER BY ts", params).fetchall()
        return [dict(r) for r in rows]

    # -- equity / decisions / stats ---------------------------------------------
    def insert_equity_snapshot(self, ts: float, equity: float, cash: float, mode: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO equity_snapshots (ts, equity, cash, mode) "
                "VALUES (?,?,?,?)", (ts, equity, cash, mode))
            self._conn.commit()

    def equity_curve(self, since_ts: float = 0.0) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM equity_snapshots WHERE ts>=? ORDER BY ts", (since_ts,)
            ).fetchall()
        return [dict(r) for r in rows]

    def insert_decision(self, ts: float, strategy: str, kind: str, payload: dict) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO decisions (ts, strategy, kind, payload) VALUES (?,?,?,?)",
                (ts, strategy, kind, json.dumps(payload)))
            self._conn.commit()

    def decisions(self, limit: int = 100, strategy: Optional[str] = None) -> list[dict]:
        q = "SELECT * FROM decisions"
        params: list[Any] = []
        if strategy is not None:
            q += " WHERE strategy=?"
            params.append(strategy)
        q += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(q, params).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["payload"] = json.loads(d["payload"])
            out.append(d)
        return out

    def last_decision_ts(self, kind: str, strategy: str) -> Optional[float]:
        with self._lock:
            row = self._conn.execute(
                "SELECT MAX(ts) AS ts FROM decisions WHERE kind=? AND strategy=?",
                (kind, strategy)).fetchone()
        return row["ts"] if row and row["ts"] is not None else None

    # -- checkpoints ---------------------------------------------------------
    def get_checkpoint(self, key: str) -> Optional[str]:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM fetch_checkpoints WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None

    def set_checkpoint(self, key: str, value: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO fetch_checkpoints (key, value) VALUES (?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
            self._conn.commit()
