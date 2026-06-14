#!/usr/bin/env python
"""Fantasy Basketball — NBA game-log ingestion CLI.

Usage:
    python ingest.py backfill            # load the last 4 seasons (resumable)
    python ingest.py backfill --seasons 6
    python ingest.py update              # nightly: pull the current season
    python ingest.py status              # what's in the store right now

The store is a single DuckDB file at data/fbball.duckdb. Every run is safe
to repeat — writes are idempotent on (player_id, game_id).
"""

import argparse
import datetime as dt
import os

from fbball import db, ingest, seasons

DEFAULT_DB = os.path.join(os.path.dirname(__file__), "data", "fbball.duckdb")


def _print_status(con) -> None:
    s = ingest.summary(con)
    print(f"  total game-log rows : {s['total_rows']:,}")
    if s["per_season"]:
        print("  rows per season     :")
        for season, n in s["per_season"].items():
            print(f"      {season} : {n:,}")
    cp = s["checkpoint"]
    if cp:
        print(f"  checkpoint          : {cp['last_season']} (through {cp['last_date']})")
    else:
        print("  checkpoint          : none yet")


def cmd_backfill(args, con) -> None:
    today = dt.date.today()
    season_list = seasons.recent_seasons(args.seasons, today=today)
    current = seasons.current_season(today)
    print(f"Backfilling seasons: {', '.join(season_list)}")
    new = ingest.backfill(con, season_list, current_season=current)
    print(f"Done. {new:,} new rows.")
    _print_status(con)


def cmd_update(args, con) -> None:
    today = dt.date.today()
    season = seasons.current_season(today)
    print(f"Updating current season: {season}")
    new = ingest.update(con, season)
    print(f"Done. {new:,} new game(s).")
    _print_status(con)


def cmd_reference(args, con) -> None:
    print("Loading reference data (teams + players + roster positions)...")
    result = ingest.load_reference(con)
    print(
        f"Done. {result['teams']} teams, {result['players']:,} players "
        f"(+{result['added_from_logs']} recovered from game logs, "
        f"{result['enriched']:,} enriched with position/team)."
    )


DEFAULT_LEAGUE_KEY = "466.l.79957"  # "The Best Time of Year" — 9-cat H2H


def cmd_yahoo(args, con) -> None:
    print(f"Pulling Yahoo league {args.league}...")
    result = ingest.pull_yahoo_league(con, args.league)
    print(
        f"Done. {result['teams']} teams, {result['roster_spots']} roster spots. "
        f"Your team: {result['my_team']}."
    )


def cmd_status(args, con) -> None:
    print("Store status:")
    _print_status(con)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="NBA game-log ingestion")
    parser.add_argument("--db", default=DEFAULT_DB, help="DuckDB file path")
    sub = parser.add_subparsers(dest="command", required=True)

    p_back = sub.add_parser("backfill", help="one-time historical load")
    p_back.add_argument("--seasons", type=int, default=4, help="how many seasons")
    p_back.set_defaults(func=cmd_backfill)

    p_up = sub.add_parser("update", help="nightly incremental for current season")
    p_up.set_defaults(func=cmd_update)

    p_ref = sub.add_parser("reference", help="load team + player reference tables")
    p_ref.set_defaults(func=cmd_reference)

    p_yh = sub.add_parser("yahoo", help="pull your Yahoo league rosters")
    p_yh.add_argument("--league", default=DEFAULT_LEAGUE_KEY, help="Yahoo league_key")
    p_yh.set_defaults(func=cmd_yahoo)

    p_st = sub.add_parser("status", help="show what's in the store")
    p_st.set_defaults(func=cmd_status)

    args = parser.parse_args(argv)
    os.makedirs(os.path.dirname(args.db), exist_ok=True)
    con = db.connect(args.db)
    try:
        args.func(args, con)
    finally:
        con.close()


if __name__ == "__main__":
    main()
