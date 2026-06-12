"""Phase 1 end-to-end demo against resmap_test: ingest a market, re-ingest
unchanged (no snapshot), then simulate a venue rule edit and show the
rule_change_events row that falls out.

    python -m scripts.verify_phase1
"""
from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

from ingest.core import MarketRecord, ingest


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    load_dotenv()
    dsn = os.environ.get("TEST_DATABASE_URL")
    if not dsn:
        print("TEST_DATABASE_URL not set — see .env.example", file=sys.stderr)
        return 1

    import psycopg
    conn = psycopg.connect(dsn)

    def rec(rules: str) -> MarketRecord:
        return MarketRecord(
            venue_code="polymarket",
            venue_market_id="0xVERIFY_PHASE1_DEMO",
            title="Phase-1 verification demo market",
            raw_rules=rules,
            status="open",
        )

    print("1) first ingest:")
    print("   ", ingest(conn, [rec("Resolves YES if X happens by 11:59pm ET.")]))
    print("2) identical re-ingest (must be unchanged=1, no new snapshot):")
    print("   ", ingest(conn, [rec("Resolves YES if X happens by 11:59pm ET.")]))
    print("3) venue edits the cutoff mid-market (must be rule_changes=1):")
    print("   ", ingest(conn, [rec("Resolves YES if X happens by 6:00pm ET.")]))

    with conn.cursor() as cur:
        cur.execute("""
            SELECT e.detected_at, e.severity,
                   ps.raw_rules AS prev_rules, ns.raw_rules AS new_rules
            FROM rule_change_events e
            JOIN rule_snapshots ps ON ps.snapshot_id = e.prev_snapshot_id
            JOIN rule_snapshots ns ON ns.snapshot_id = e.new_snapshot_id
            JOIN markets m ON m.market_id = e.market_id
            WHERE m.venue_market_id = '0xVERIFY_PHASE1_DEMO'
            ORDER BY e.detected_at DESC LIMIT 1
        """)
        row = cur.fetchone()

    if not row:
        print("FAIL: no rule_change_events row found", file=sys.stderr)
        return 1

    detected_at, severity, prev_rules, new_rules = row
    print("\nrule_change_events row:")
    print(f"  detected_at: {detected_at}")
    print(f"  severity:    {severity}")
    print(f"  prev rules:  {prev_rules}")
    print(f"  new rules:   {new_rules}")
    print("\nPhase 1 verification PASSED")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
