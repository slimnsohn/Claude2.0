"""
Ingest run loop. Calls each venue adapter and feeds records to the core.
Run on a schedule (cron / Task Scheduler). One transaction-batch per venue.

    python -m ingest.run                          # all venues
    python -m ingest.run --venue polymarket       # one venue
    python -m ingest.run --max-pages 5            # cap pages per venue (testing)

Env: DATABASE_URL must be set (see .env.example; .env is auto-loaded).
"""
from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

from ingest.adapters import MissingCredentialsError, gemini, kalshi, polymarket
from ingest.core import ingest

VENUES = {"polymarket": polymarket, "kalshi": kalshi, "gemini": gemini}


def get_conn():
    import psycopg  # psycopg v3
    dsn = os.environ["DATABASE_URL"]
    return psycopg.connect(dsn)


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="ResMap ingest loop")
    parser.add_argument("--venue", choices=[*VENUES, "all"], default="all")
    parser.add_argument("--max-pages", type=int, default=None,
                        help="cap pages fetched per venue (testing/throttling)")
    args = parser.parse_args(argv)

    selected = VENUES if args.venue == "all" else {args.venue: VENUES[args.venue]}

    conn = get_conn()
    total = {"new_markets": 0, "rule_changes": 0, "unchanged": 0}
    try:
        for name, adapter in selected.items():
            try:
                records = adapter.fetch_markets(status="open",
                                                max_pages=args.max_pages)
                stats = ingest(conn, records)
                print(f"[{name}] {stats}")
                for k in total:
                    total[k] += stats[k]
            except MissingCredentialsError as e:
                print(f"[{name}] no credentials — skipping ({e})")
            except NotImplementedError:
                print(f"[{name}] adapter not implemented yet — skipping")
            except Exception as e:
                conn.rollback()
                print(f"[{name}] ERROR: {e}", file=sys.stderr)
    finally:
        conn.close()
    print(f"[total] {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
