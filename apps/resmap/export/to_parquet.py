"""
Export Postgres → partitioned Parquet for DuckDB / analytical buyers (the data
product for backtesters and researchers). Postgres stays the source of truth;
this is a periodic one-way snapshot (PG → Parquet, never the reverse).

    python -m export.to_parquet --out ./export/parquet

Layout (markets / parsed_rules / rule_changes partition by venue for cheap
DuckDB pruning; sources / equivalences are flat):
    parquet/markets/venue=kalshi/*.parquet
    parquet/parsed_rules/venue=polymarket/*.parquet
    parquet/equivalences/*.parquet
    parquet/rule_changes/venue=kalshi/*.parquet
    parquet/sources/*.parquet

Consume from DuckDB, e.g.:
    SELECT * FROM read_parquet('parquet/equivalences/*.parquet') WHERE match_type='false_friend';

The parsed-rules export resolves the settlement source THROUGH sources.merged_into,
so buyers see the curated canonical authority, not raw extraction wording.
"""
from __future__ import annotations

import argparse
import os
import shutil
import uuid

import pyarrow as pa
import pyarrow.parquet as pq

# layer -> (SQL, partition_cols). Order doesn't matter; each is independent.
LAYERS: dict[str, tuple[str, list[str] | None]] = {
    "markets": ("""
        SELECT v.code AS venue, m.market_id, m.venue_market_id, m.title,
               m.category, m.status, m.opened_at, m.closes_at, m.resolved_at,
               m.outcome, m.first_seen_at, m.last_seen_at
        FROM markets m JOIN venues v USING (venue_id)
    """, ["venue"]),

    "parsed_rules": ("""
        SELECT v.code AS venue, m.venue_market_id,
               COALESCE(canon.canonical_name, s.canonical_name) AS authoritative_source,
               s2.source_type, p.source_fallback, p.resolution_logic,
               p.cutoff_time, p.cutoff_basis, p.tie_handling, p.revision_handling,
               p.threshold_def, p.confidence, p.reviewed, p.is_stale, p.created_at
        FROM parsed_rules p
        JOIN markets m USING (market_id)
        JOIN venues v USING (venue_id)
        LEFT JOIN sources s     ON s.source_id = p.source_id
        LEFT JOIN sources canon ON canon.source_id = s.merged_into
        LEFT JOIN sources s2     ON s2.source_id = COALESCE(s.merged_into, p.source_id)
    """, ["venue"]),

    "equivalences": ("""
        SELECT e.equivalence_id, e.market_a_id, e.market_b_id, e.match_type,
               e.divergence_axes, e.divergence_notes, e.risk_score,
               e.detected_by, e.created_at, e.updated_at
        FROM equivalences e
    """, None),

    "rule_changes": ("""
        SELECT v.code AS venue, m.venue_market_id, e.detected_at, e.severity,
               e.diff_summary, prev.raw_rules AS prev_rules, new.raw_rules AS new_rules
        FROM rule_change_events e
        JOIN markets m USING (market_id)
        JOIN venues v USING (venue_id)
        LEFT JOIN rule_snapshots prev ON prev.snapshot_id = e.prev_snapshot_id
        JOIN rule_snapshots new ON new.snapshot_id = e.new_snapshot_id
    """, ["venue"]),

    "sources": ("""
        SELECT source_id, canonical_name, source_type, merged_into, notes
        FROM sources
    """, None),
}


def _clean(value):
    """psycopg returns UUID objects pyarrow can't infer — stringify them.
    datetimes, numbers, bools, None, and TEXT[] lists pass through."""
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def _dump(conn, out_dir: str, layer: str, sql: str,
          partition_cols: list[str] | None) -> int:
    with conn.cursor() as cur:
        cur.execute(sql)
        cols = [c.name for c in cur.description]
        rows = [dict(zip(cols, (_clean(v) for v in r))) for r in cur.fetchall()]

    path = os.path.join(out_dir, layer)
    if os.path.isdir(path):
        shutil.rmtree(path)          # fresh snapshot each run
    if not rows:
        return 0

    table = pa.Table.from_pylist(rows)
    pq.write_to_dataset(table, root_path=path, partition_cols=partition_cols)
    return len(rows)


def export(conn, out_dir: str = "./export/parquet") -> dict:
    """Snapshot the structured layers to Parquet. Returns {layer: row_count}."""
    os.makedirs(out_dir, exist_ok=True)
    return {layer: _dump(conn, out_dir, layer, sql, parts)
            for layer, (sql, parts) in LAYERS.items()}


def main(argv: list[str] | None = None) -> int:
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    from dotenv import load_dotenv
    load_dotenv()
    parser = argparse.ArgumentParser(description="ResMap Postgres → Parquet export")
    parser.add_argument("--out", default="./export/parquet")
    args = parser.parse_args(argv)

    import psycopg
    conn = psycopg.connect(os.environ["DATABASE_URL"])
    try:
        stats = export(conn, args.out)
    finally:
        conn.close()
    total = sum(stats.values())
    print(f"[export] {stats} → {args.out} ({total} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
