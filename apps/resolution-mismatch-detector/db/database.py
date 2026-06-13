"""SQLite database helper for the resolution mismatch detector."""

import sqlite3
from datetime import datetime
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DB_PATH, SCHEMA_PATH


class Database:
    def __init__(self, db_path=None):
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_schema()

    def init_schema(self):
        schema_sql = SCHEMA_PATH.read_text()
        conn = self._connect()
        conn.executescript(schema_sql)
        conn.commit()
        conn.close()

    def _connect(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def __enter__(self):
        self._conn = self._connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self._conn.commit()
        self._conn.close()
        self._conn = None
        return False

    # ── Helpers ──────────────────────────────────────────────

    @staticmethod
    def _row_to_dict(row):
        return dict(row) if row else None

    @staticmethod
    def _rows_to_list(rows):
        return [dict(r) for r in rows]

    @staticmethod
    def _now():
        return datetime.utcnow().isoformat()

    # ── Markets ─────────────────────────────────────────────

    def upsert_market(self, market: dict):
        market.setdefault("first_seen_at", self._now())
        market.setdefault("last_updated_at", self._now())
        cols = list(market.keys())
        placeholders = ", ".join(["?"] * len(cols))
        col_names = ", ".join(cols)
        sql = f"INSERT OR REPLACE INTO markets ({col_names}) VALUES ({placeholders})"
        conn = self._connect()
        conn.execute(sql, [market[c] for c in cols])
        conn.commit()
        conn.close()

    def get_market(self, market_id: str) -> dict | None:
        conn = self._connect()
        row = conn.execute("SELECT * FROM markets WHERE id = ?", (market_id,)).fetchone()
        conn.close()
        return self._row_to_dict(row)

    def get_markets(self, platform=None, min_volume=None, active_only=True) -> list[dict]:
        sql = "SELECT * FROM markets WHERE 1=1"
        params = []
        if platform:
            sql += " AND platform = ?"
            params.append(platform)
        if min_volume is not None:
            sql += " AND volume >= ?"
            params.append(min_volume)
        if active_only:
            sql += " AND (end_date IS NULL OR end_date >= ?)"
            params.append(self._now())
        sql += " ORDER BY volume DESC"
        conn = self._connect()
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return self._rows_to_list(rows)

    def get_cache_stats(self) -> dict:
        """Get cache statistics: total markets, last fetch time, unanalyzed count."""
        conn = self._connect()
        total = conn.execute("SELECT COUNT(*) FROM markets").fetchone()[0]
        poly = conn.execute("SELECT COUNT(*) FROM markets WHERE platform='polymarket'").fetchone()[0]
        kalshi = conn.execute("SELECT COUNT(*) FROM markets WHERE platform='kalshi'").fetchone()[0]
        last_updated = conn.execute("SELECT MAX(last_updated_at) FROM markets").fetchone()[0]
        analyzed = conn.execute(
            "SELECT COUNT(DISTINCT market_id) FROM analysis_results"
        ).fetchone()[0]
        conn.close()
        return {
            "total_markets": total,
            "polymarket": poly,
            "kalshi": kalshi,
            "analyzed": analyzed,
            "unanalyzed": total - analyzed,
            "last_fetched": last_updated,
        }

    def get_unanalyzed_markets(self, min_volume=None) -> list[dict]:
        """Get markets that have no analysis results yet."""
        sql = """SELECT m.* FROM markets m
                 LEFT JOIN analysis_results a ON m.id = a.market_id
                 WHERE a.id IS NULL"""
        params = []
        if min_volume is not None:
            sql += " AND m.volume >= ?"
            params.append(min_volume)
        sql += " ORDER BY m.volume DESC"
        conn = self._connect()
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return self._rows_to_list(rows)

    def get_stale_markets(self) -> list[dict]:
        """Get markets where rules changed since last analysis."""
        sql = """SELECT m.* FROM markets m
                 JOIN rule_snapshots rs ON m.id = rs.market_id
                 JOIN analysis_results a ON m.id = a.market_id
                 WHERE rs.rules_hash != a.rules_hash
                 AND rs.snapshot_at > a.analyzed_at
                 GROUP BY m.id
                 ORDER BY m.volume DESC"""
        conn = self._connect()
        rows = conn.execute(sql).fetchall()
        conn.close()
        return self._rows_to_list(rows)

    # ── Rule Snapshots ──────────────────────────────────────

    def insert_rule_snapshot(self, market_id, rules, rules_hash):
        sql = """INSERT INTO rule_snapshots (market_id, resolution_rules, snapshot_at, rules_hash)
                 VALUES (?, ?, ?, ?)"""
        conn = self._connect()
        conn.execute(sql, (market_id, rules, self._now(), rules_hash))
        conn.commit()
        conn.close()

    def get_latest_snapshot(self, market_id) -> dict | None:
        sql = """SELECT * FROM rule_snapshots
                 WHERE market_id = ? ORDER BY snapshot_at DESC LIMIT 1"""
        conn = self._connect()
        row = conn.execute(sql, (market_id,)).fetchone()
        conn.close()
        return self._row_to_dict(row)

    # ── Analysis Results ────────────────────────────────────

    def insert_analysis(self, analysis: dict):
        analysis.setdefault("analyzed_at", self._now())
        cols = list(analysis.keys())
        placeholders = ", ".join(["?"] * len(cols))
        col_names = ", ".join(cols)
        sql = f"INSERT INTO analysis_results ({col_names}) VALUES ({placeholders})"
        conn = self._connect()
        conn.execute(sql, [analysis[c] for c in cols])
        conn.commit()
        conn.close()

    def get_latest_analysis(self, market_id) -> dict | None:
        sql = """SELECT * FROM analysis_results
                 WHERE market_id = ? ORDER BY analyzed_at DESC LIMIT 1"""
        conn = self._connect()
        row = conn.execute(sql, (market_id,)).fetchone()
        conn.close()
        return self._row_to_dict(row)

    def get_analyses(self, severity=None, min_priority=None) -> list[dict]:
        sql = "SELECT * FROM analysis_results WHERE 1=1"
        params = []
        if severity:
            sql += " AND severity = ?"
            params.append(severity)
        if min_priority is not None:
            sql += " AND priority_score >= ?"
            params.append(min_priority)
        sql += " ORDER BY priority_score DESC"
        conn = self._connect()
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return self._rows_to_list(rows)

    # ── Cross-Platform Matches ──────────────────────────────

    def insert_cross_match(self, match: dict):
        match.setdefault("detected_at", self._now())
        match.setdefault("last_checked_at", self._now())
        cols = list(match.keys())
        placeholders = ", ".join(["?"] * len(cols))
        col_names = ", ".join(cols)
        sql = f"INSERT INTO cross_platform_matches ({col_names}) VALUES ({placeholders})"
        conn = self._connect()
        conn.execute(sql, [match[c] for c in cols])
        conn.commit()
        conn.close()

    def get_cross_matches(self, min_confidence=None) -> list[dict]:
        sql = "SELECT * FROM cross_platform_matches WHERE 1=1"
        params = []
        if min_confidence is not None:
            sql += " AND match_confidence >= ?"
            params.append(min_confidence)
        sql += " ORDER BY match_confidence DESC"
        conn = self._connect()
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return self._rows_to_list(rows)

    # ── Positions ───────────────────────────────────────────

    def upsert_position(self, **kwargs):
        kwargs.setdefault("entered_at", self._now())
        cols = list(kwargs.keys())
        placeholders = ", ".join(["?"] * len(cols))
        col_names = ", ".join(cols)
        sql = f"INSERT OR REPLACE INTO positions ({col_names}) VALUES ({placeholders})"
        conn = self._connect()
        conn.execute(sql, [kwargs[c] for c in cols])
        conn.commit()
        conn.close()

    def get_position(self, market_id) -> dict | None:
        sql = "SELECT * FROM positions WHERE market_id = ? ORDER BY entered_at DESC LIMIT 1"
        conn = self._connect()
        row = conn.execute(sql, (market_id,)).fetchone()
        conn.close()
        return self._row_to_dict(row)

    def get_all_positions(self) -> list[dict]:
        conn = self._connect()
        rows = conn.execute("SELECT * FROM positions ORDER BY entered_at DESC").fetchall()
        conn.close()
        return self._rows_to_list(rows)

    def has_position(self, market_id) -> bool:
        conn = self._connect()
        row = conn.execute(
            "SELECT 1 FROM positions WHERE market_id = ? AND exited_at IS NULL LIMIT 1",
            (market_id,),
        ).fetchone()
        conn.close()
        return row is not None

    # ── Resolution Audit ────────────────────────────────────

    def insert_resolution_audit(self, audit: dict):
        cols = list(audit.keys())
        placeholders = ", ".join(["?"] * len(cols))
        col_names = ", ".join(cols)
        sql = f"INSERT INTO resolution_audit ({col_names}) VALUES ({placeholders})"
        conn = self._connect()
        conn.execute(sql, [audit[c] for c in cols])
        conn.commit()
        conn.close()

    def get_all_audits(self) -> list[dict]:
        conn = self._connect()
        rows = conn.execute("SELECT * FROM resolution_audit ORDER BY resolved_at DESC").fetchall()
        conn.close()
        return self._rows_to_list(rows)

    # ── Prompt Evals ────────────────────────────────────────

    def insert_prompt_eval(self, **kwargs):
        kwargs.setdefault("eval_run_at", self._now())
        cols = list(kwargs.keys())
        placeholders = ", ".join(["?"] * len(cols))
        col_names = ", ".join(cols)
        sql = f"INSERT INTO prompt_evals ({col_names}) VALUES ({placeholders})"
        conn = self._connect()
        conn.execute(sql, [kwargs[c] for c in cols])
        conn.commit()
        conn.close()

    def get_prompt_eval_results(self, prompt_version) -> list[dict]:
        sql = "SELECT * FROM prompt_evals WHERE prompt_version = ? ORDER BY eval_run_at DESC"
        conn = self._connect()
        rows = conn.execute(sql, (prompt_version,)).fetchall()
        conn.close()
        return self._rows_to_list(rows)

    # ── Dismissed Alerts ────────────────────────────────────

    def dismiss_alert(self, market_id, dismissed_at, reason=None):
        sql = "INSERT INTO dismissed_alerts (market_id, dismissed_at, reason) VALUES (?, ?, ?)"
        conn = self._connect()
        conn.execute(sql, (market_id, dismissed_at, reason))
        conn.commit()
        conn.close()

    def is_dismissed(self, market_id) -> bool:
        conn = self._connect()
        row = conn.execute(
            "SELECT 1 FROM dismissed_alerts WHERE market_id = ? LIMIT 1", (market_id,)
        ).fetchone()
        conn.close()
        return row is not None

    # ── Watchlist ───────────────────────────────────────────

    def add_to_watchlist(self, market_id, added_at, target_price=None, notes=None):
        sql = """INSERT INTO watchlist (market_id, added_at, target_price, notes)
                 VALUES (?, ?, ?, ?)"""
        conn = self._connect()
        conn.execute(sql, (market_id, added_at, target_price, notes))
        conn.commit()
        conn.close()

    def get_watchlist(self) -> list[dict]:
        conn = self._connect()
        rows = conn.execute("SELECT * FROM watchlist ORDER BY added_at DESC").fetchall()
        conn.close()
        return self._rows_to_list(rows)

    # ── Source Monitors ─────────────────────────────────────

    def upsert_source_monitor(self, source_name, **kwargs):
        kwargs["source_name"] = source_name
        kwargs.setdefault("last_checked_at", self._now())
        cols = list(kwargs.keys())
        placeholders = ", ".join(["?"] * len(cols))
        col_names = ", ".join(cols)
        sql = f"INSERT OR REPLACE INTO source_monitors ({col_names}) VALUES ({placeholders})"
        conn = self._connect()
        conn.execute(sql, [kwargs[c] for c in cols])
        conn.commit()
        conn.close()

    def get_source_monitor(self, source_name) -> dict | None:
        sql = "SELECT * FROM source_monitors WHERE source_name = ?"
        conn = self._connect()
        row = conn.execute(sql, (source_name,)).fetchone()
        conn.close()
        return self._row_to_dict(row)

    def update_source_monitor(self, source_name, content_hash):
        now = self._now()
        sql = """UPDATE source_monitors
                 SET content_hash = ?, last_checked_at = ?, last_updated_at = ?
                 WHERE source_name = ?"""
        conn = self._connect()
        conn.execute(sql, (content_hash, now, now, source_name))
        conn.commit()
        conn.close()
