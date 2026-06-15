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
    print(
        f"Bridged {result['matched']}/{result['roster_spots']} players to NBA ids."
    )
    if result["unmatched"]:
        print("  Unmatched (NULL nba_player_id — add an alias if needed):")
        for name in result["unmatched"]:
            print(f"    - {name}")


def cmd_freeagents(args, con) -> None:
    print(f"Pulling free agents for league {args.league}...")
    result = ingest.pull_free_agents(con, args.league)
    print(f"Done. {result['fetched']} free agents fetched, "
          f"{result['matched']} bridged to NBA ids.")
    if result["unmatched"]:
        print(f"  {len(result['unmatched'])} unmatched (no NBA stats link):")
        for name in result["unmatched"][:15]:
            print(f"    - {name}")


def cmd_history(args, con) -> None:
    from fbball import yahoo_history
    print(f"Pulling Yahoo league history (renew chain from {args.league})...")
    totals = yahoo_history.pull_league_history(
        con, start_key=args.league, log=print)
    print(f"\nDone. {totals['seasons']} seasons | {totals['teams']} team-seasons | "
          f"{totals['draft']} draft picks | {totals['roster']} final-roster spots.")


def cmd_owners(args, con) -> None:
    from fbball import yahoo_history
    n = yahoo_history.rebuild_owner_identity(con)
    if n == 0:
        print("No league history stored. Run:  python ingest.py history")
        return
    rows = con.execute(
        """
        SELECT o.owner_label, COUNT(DISTINCT o.season) n_seasons,
               MIN(o.season) ymin, MAX(o.season) ymax,
               COUNT(DISTINCT t.team_name) n_names,
               COUNT(DISTINCT NULLIF(t.manager_email,'')) n_emails
        FROM yh_owner_identity o JOIN yh_teams t USING (season, team_key)
        GROUP BY o.owner_label ORDER BY n_seasons DESC, ymin
        """
    ).fetchall()
    print(f"Canonical owners (team-name continuity, bridging email/nickname): {len(rows)}\n")
    print(f"  {'Owner (team)':<24} {'Seas':>4}  {'Span':<11} {'Names':>5} {'Emails':>6}")
    for r in rows:
        print(f"  {(r[0] or '')[:24]:<24} {r[1]:>4}  {str(r[2])+'-'+str(r[3]):<11} {r[4]:>5} {r[5]:>6}")


def cmd_prep(args, con) -> None:
    """Offseason one-shot: pull the season that just finished + refresh reference.

    Run this in the offseason (≈April–September). It targets the current
    season label, which in the offseason is the season that just completed.
    """
    today = dt.date.today()
    season = seasons.current_season(today)
    print(f"Offseason prep - pulling completed season {season} + reference data...")
    new = ingest.update(con, season)
    print(f"  game logs : {new:,} new rows")
    ref = ingest.load_reference(con)
    print(f"  reference : {ref['teams']} teams, {ref['players']:,} players "
          f"({ref['enriched']:,} with positions)")
    _print_status(con)
    print("\nReady. Build your board:  python draft.py")


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

    p_fa = sub.add_parser("freeagents", help="pull the league free-agent pool")
    p_fa.add_argument("--league", default=DEFAULT_LEAGUE_KEY, help="Yahoo league_key")
    p_fa.set_defaults(func=cmd_freeagents)

    p_hist = sub.add_parser(
        "history", help="pull the full Yahoo league history lake (all past seasons)")
    p_hist.add_argument("--league", default=DEFAULT_LEAGUE_KEY, help="current league_key")
    p_hist.set_defaults(func=cmd_history)

    p_own = sub.add_parser(
        "owners", help="rebuild + show canonical owner identity (team-name continuity)")
    p_own.set_defaults(func=cmd_owners)

    p_prep = sub.add_parser(
        "prep", help="offseason one-shot: pull last season + refresh reference")
    p_prep.set_defaults(func=cmd_prep)

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
