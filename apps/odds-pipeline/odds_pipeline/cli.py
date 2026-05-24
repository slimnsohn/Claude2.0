"""odds_pipeline CLI: init | pull-odds | pull-results | build | status."""
import argparse
import json
import sys
from datetime import datetime, timezone
from dateutil import parser as dtparser

from odds_pipeline import config
from odds_pipeline.odds_source.client import TheOddsApiClient
from odds_pipeline.odds_source import ingest as odds_ingest
from odds_pipeline.store import migrate, seed


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


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
            started = _utc_now_iso()
            result = odds_ingest.pull_odds_for_sport(
                client=client, sport=sport,
                date_from=date_from, date_to=date_to,
                regions=config.REGIONS, archive_root=config.RAW_ODDS_DIR,
                limit=args.limit,
            )
            completed = _utc_now_iso()
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
    from odds_pipeline.results_sources import ingest as r_ingest
    from odds_pipeline.results_sources.nba import NBAResultsAdapter
    from odds_pipeline.results_sources.nfl import NFLResultsAdapter
    from odds_pipeline.results_sources.nhl import NHLResultsAdapter
    from odds_pipeline.results_sources.mlb import MLBResultsAdapter
    from odds_pipeline.results_sources.ncaab import NCAABResultsAdapter
    from odds_pipeline.results_sources.ncaaf import NCAAFResultsAdapter

    adapters = {
        "NBA": NBAResultsAdapter, "NFL": NFLResultsAdapter,
        "NHL": NHLResultsAdapter, "MLB": MLBResultsAdapter,
        "NCAAB": NCAABResultsAdapter, "NCAAF": NCAAFResultsAdapter,
    }
    sports = [s.strip() for s in args.sport.split(",")]
    date_from = dtparser.isoparse(args.date_from).date()
    date_to = dtparser.isoparse(args.date_to).date()

    conn = migrate.connect(config.DB_PATH)
    try:
        for sport in sports:
            adapter_cls = adapters.get(sport)
            if not adapter_cls:
                print(f"Unknown sport: {sport}")
                continue
            started = _utc_now_iso()
            res = r_ingest.pull_results_for_sport(
                adapter=adapter_cls(), sport=sport,
                date_from=date_from, date_to=date_to,
                archive_root=config.RAW_RESULTS_DIR,
            )
            completed = _utc_now_iso()
            status = "ok" if not res.errors else "partial"
            conn.execute(
                "INSERT INTO ingest_runs (run_type, sport, params_json, credits_used, "
                "started_at, completed_at, status, error_message) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("results_fetch", sport,
                 json.dumps({"from": args.date_from, "to": args.date_to}),
                 None, started, completed, status, "; ".join(res.errors)[:500] or None),
            )
            conn.commit()
            print(f"[{sport}] results archived={res.games_archived}")
    finally:
        conn.close()


def _cmd_build(args):
    from odds_pipeline.store import derive
    derive.build_all(
        db_path=config.DB_PATH,
        odds_root=config.RAW_ODDS_DIR,
        results_root=config.RAW_RESULTS_DIR,
    )
    conn = migrate.connect(config.DB_PATH)
    try:
        games_count = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
        odds_count = conn.execute("SELECT COUNT(*) FROM odds_snapshots").fetchone()[0]
        scores_count = conn.execute("SELECT COUNT(*) FROM scores").fetchone()[0]
        print(f"games={games_count} odds_snapshots={odds_count} scores={scores_count}")
        unmatched = conn.execute(
            "SELECT game_id FROM games WHERE game_id NOT IN (SELECT DISTINCT game_id FROM scores) "
            "AND results_source_game_id IS NULL LIMIT 10"
        ).fetchall()
        if unmatched:
            print(f"Unmatched (no scores) sample: {[u[0] for u in unmatched]}")
    finally:
        conn.close()


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
