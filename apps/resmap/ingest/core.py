"""
ResMap ingestion: pull markets + rules from a venue, store registry rows, and
append rule snapshots ONLY when the settlement text actually changes.

This is the heart of the "living dataset" — the change-detection loop. Run it on
a schedule (cron / a small worker). It is intentionally venue-agnostic: each venue
gets an adapter that yields a common `MarketRecord`. Swap the rented-feed adapter
for direct venue APIs later without touching this core.
"""
from __future__ import annotations
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Optional


# ── common record every adapter must yield ──────────────────────────────────
@dataclass
class MarketRecord:
    venue_code: str
    venue_market_id: str
    title: str
    raw_rules: str                  # verbatim settlement criteria text
    category: Optional[str] = None
    opened_at: Optional[datetime] = None
    closes_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    outcome: Optional[str] = None
    status: str = "open"
    raw_payload: dict = field(default_factory=dict)


def normalize_rules(text: str) -> str:
    """Normalize before hashing so cosmetic whitespace/casing churn doesn't
    masquerade as a real rule change."""
    return " ".join(text.split()).strip().lower()


def content_hash(text: str) -> str:
    return hashlib.sha256(normalize_rules(text).encode("utf-8")).hexdigest()


# ── core upsert + change-detection ──────────────────────────────────────────
def ingest(conn, records: Iterable[MarketRecord], commit_every: int = 500) -> dict:
    """
    Returns counts: {'new_markets', 'rule_changes', 'unchanged'}.
    `conn` is a psycopg connection.

    Commits every `commit_every` records (each record's work is self-contained,
    so a batch boundary is always consistent). A mid-stream failure on a long
    ingest therefore keeps everything before the last boundary — the next run
    resumes idempotently rather than redoing tens of thousands of markets.
    Pass commit_every=0 to commit only once at the end.
    """
    stats = {"new_markets": 0, "rule_changes": 0, "unchanged": 0}
    now = datetime.now(timezone.utc)
    seen = 0

    with conn.cursor() as cur:
        for rec in records:
            seen += 1
            cur.execute("SELECT venue_id FROM venues WHERE code = %s", (rec.venue_code,))
            row = cur.fetchone()
            if not row:
                raise ValueError(f"unknown venue: {rec.venue_code}")
            venue_id = row[0]

            # upsert market registry row, get its id + whether it's new
            cur.execute(
                """
                INSERT INTO markets (venue_id, venue_market_id, title, category,
                                     opened_at, closes_at, resolved_at, outcome,
                                     status, last_seen_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (venue_id, venue_market_id) DO UPDATE
                  SET title = EXCLUDED.title,
                      category = EXCLUDED.category,
                      closes_at = EXCLUDED.closes_at,
                      resolved_at = EXCLUDED.resolved_at,
                      outcome = EXCLUDED.outcome,
                      status = EXCLUDED.status,
                      last_seen_at = EXCLUDED.last_seen_at
                RETURNING market_id, (xmax = 0) AS inserted
                """,
                (venue_id, rec.venue_market_id, rec.title, rec.category,
                 rec.opened_at, rec.closes_at, rec.resolved_at, rec.outcome,
                 rec.status, now),
            )
            market_id, inserted = cur.fetchone()
            if inserted:
                stats["new_markets"] += 1

            # change detection: compare hash vs latest snapshot
            h = content_hash(rec.raw_rules)
            cur.execute(
                """
                SELECT snapshot_id, content_hash
                FROM rule_snapshots
                WHERE market_id = %s
                ORDER BY fetched_at DESC
                LIMIT 1
                """,
                (market_id,),
            )
            prev = cur.fetchone()

            if prev and prev[1] == h:
                stats["unchanged"] += 1
                if commit_every and seen % commit_every == 0:
                    conn.commit()
                continue  # nothing changed; don't write a snapshot

            # rules are new or changed → append immutable snapshot
            cur.execute(
                """
                INSERT INTO rule_snapshots (market_id, raw_rules, content_hash, raw_payload)
                VALUES (%s,%s,%s,%s)
                RETURNING snapshot_id
                """,
                (market_id, rec.raw_rules, h, _json(rec.raw_payload)),
            )
            new_snap = cur.fetchone()[0]

            if prev:  # a genuine mid-market rule change → record the event + flag re-parse
                stats["rule_changes"] += 1
                cur.execute(
                    """
                    INSERT INTO rule_change_events (market_id, prev_snapshot_id,
                                                    new_snapshot_id, severity)
                    VALUES (%s,%s,%s,'unknown')
                    """,
                    (market_id, prev[0], new_snap),
                )
                cur.execute(
                    "UPDATE parsed_rules SET is_stale = TRUE WHERE market_id = %s",
                    (market_id,),
                )

            if commit_every and seen % commit_every == 0:
                conn.commit()  # batch boundary — durable, resumable
    conn.commit()
    return stats


def _json(d: dict):
    import json
    return json.dumps(d) if d else None
