"""odds_pipeline CLI: init | pull-odds | pull-results | build | status."""
import argparse
import json
import sqlite3
import sys
from datetime import date, datetime
from dateutil import parser as dtparser

from odds_pipeline import config, archive
from odds_pipeline.odds_source.client import TheOddsApiClient
from odds_pipeline.odds_source import ingest as odds_ingest
from odds_pipeline.store import migrate, seed


def _cmd_init(args):
    migrate.init_db(config.DB_PATH)
    seed.seed_all(config.DB_PATH)
    print(f"Initialized {config.DB_PATH}")


def _cmd_pull_odds(args):
    if not config.THE_ODDS_API_KEY:
        sys.exit("THE_ODDS_API_KEY env var not set")
    client = TheOddsApiClient(config.THE_ODDS_API_KEY)
    sports = [s.strip() for s in args.sport.split(",")]
    date_from = dtparser.isoparse(args.date_from).date()
    date_to = dtparser.isoparse(args.date_to).date()

    conn = migrate.connect(config.DB_PATH)
    try:
        for sport in sports:
            started = datetime.utcnow().isoformat()
            result = odds_ingest.pull_odds_for_sport(
                client=client, sport=sport,
                date_from=date_from, date_to=date_to,
                regions=config.REGIONS, archive_root=config.RAW_ODDS_DIR,
                limit=args.limit,
            )
            completed = datetime.utcnow().isoformat()
            status = "ok" if not result.errors else "partial"
            conn.execute(
                "INSERT INTO ingest_runs (run_type, sport, params_json, credits_used, "
                "started_at, completed_at, status, error_message) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("odds_historical", sport, json.dumps({"from": args.date_from, "to": args.date_to, "limit": args.limit}),
                 result.credits_used, started, completed, status, "; ".join(result.errors)[:500] or None),
            )
            conn.commit()
            print(f"[{sport}] processed={result.events_processed} archived={result.events_archived} "
                  f"skipped={result.events_skipped} failed={result.events_failed} credits={result.credits_used}")
    finally:
        conn.close()


def _cmd_pull_results(args):
    print("pull-results: stub — implemented in later task")


def _cmd_build(args):
    print("build: stub — implemented in later task")


def _cmd_status(args):
    conn = migrate.connect(config.DB_PATH)
    try:
        games = conn.execute("SELECT sport, COUNT(*) FROM games GROUP BY sport").fetchall()
        print("Games in DB:", dict(games))
        runs = conn.execute(
            "SELECT sport, run_type, status, credits_used, completed_at "
            "FROM ingest_runs ORDER BY run_id DESC LIMIT 10"
        ).fetchall()
        for r in runs:
            print(r)
    finally:
        conn.close()


def main(argv=None):
    p = argparse.ArgumentParser(prog="odds_pipeline")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init")

    p_odds = sub.add_parser("pull-odds")
    p_odds.add_argument("--sport", required=True, help="Comma-separated, e.g. NBA,NFL")
    p_odds.add_argument("--from", dest="date_from", required=True)
    p_odds.add_argument("--to", dest="date_to", required=True)
    p_odds.add_argument("--limit", type=int, default=None)

    p_res = sub.add_parser("pull-results")
    p_res.add_argument("--sport", required=True)
    p_res.add_argument("--from", dest="date_from", required=True)
    p_res.add_argument("--to", dest="date_to", required=True)

    sub.add_parser("build")
    sub.add_parser("status")

    args = p.parse_args(argv)
    {"init": _cmd_init, "pull-odds": _cmd_pull_odds,
     "pull-results": _cmd_pull_results, "build": _cmd_build,
     "status": _cmd_status}[args.cmd](args)
