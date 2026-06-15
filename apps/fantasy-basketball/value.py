#!/usr/bin/env python
"""Fantasy Basketball — 9-cat z-score valuation.

Usage:
    python value.py                          # top 30 overall (season value)
    python value.py --top 50
    python value.py --source recent          # rank by current form (last 15)
    python value.py --punt FT_PCT TOV        # punt build: re-rank ignoring those cats
    python value.py --mine                   # value YOUR roster vs the league pool

Values are z-scores vs the qualifying player pool. Percentage cats (FG%/FT%)
use the volume-weighted impact method. Punting a cat re-ranks for that build.
"""

import argparse
import os
import sys

from fbball import db, valuation

DEFAULT_DB = os.path.join(os.path.dirname(__file__), "data", "fbball.duckdb")
CATS = valuation.CATS


def _my_player_ids(con):
    rows = con.execute(
        "SELECT r.nba_player_id FROM yahoo_roster r JOIN yahoo_teams t USING (team_key) "
        "WHERE t.is_my_team AND r.nba_player_id IS NOT NULL"
    ).fetchall()
    return {r[0] for r in rows}


def _print_table(ranked, title):
    print(f"\n{title}\n")
    head = f"{'Rk':>3} {'Player':<22} {'GP':>3} "
    head += "".join(f"{valuation.CAT_DISPLAY[c]:>6}" for c in CATS)
    head += f" {'TOTAL':>7}"
    print(head)
    print("-" * len(head))
    for r in ranked:
        line = f"{r['rank']:>3} {r['full_name'][:22]:<22} {int(r['gp'] or 0):>3} "
        line += "".join(f"{r['zscores'][c]:>6.2f}" for c in CATS)
        line += f" {r['total_value']:>7.2f}"
        print(line)


def main(argv=None):
    p = argparse.ArgumentParser(description="9-cat z-score valuation")
    p.add_argument("--db", default=DEFAULT_DB)
    p.add_argument("--season", default=None,
                   help="season label; defaults to the latest in your data lake")
    p.add_argument("--source", choices=["season", "recent"], default="season")
    p.add_argument("--punt", nargs="*", default=[], metavar="CAT",
                   help=f"cats to punt, from: {', '.join(CATS)}")
    p.add_argument("--top", type=int, default=30)
    p.add_argument("--min-gp", type=int, default=20)
    p.add_argument("--min-min", type=float, default=10.0)
    p.add_argument("--mine", action="store_true", help="show only your roster")
    args = p.parse_args(argv)

    punt = set(args.punt)
    bad = punt - set(CATS)
    if bad:
        sys.exit(f"Unknown punt cat(s): {', '.join(bad)}. Choose from {', '.join(CATS)}")

    con = db.connect(args.db)
    try:
        season = args.season or db.latest_season(con)
        ranked = valuation.rank_from_db(
            con, season=season, source=args.source,
            min_gp=args.min_gp, min_min=args.min_min, punt=punt,
        )
        label = f"{args.source} value, {season}"
        if punt:
            label += f"  |  PUNT: {', '.join(valuation.CAT_DISPLAY[c] for c in punt)}"

        if args.mine:
            mine = _my_player_ids(con)
            ranked = [r for r in ranked if r["player_id"] in mine]
            _print_table(ranked, f"YOUR ROSTER — {label} (rank = overall pool rank)")
        else:
            _print_table(ranked[: args.top], f"TOP {args.top} — {label}")
    finally:
        con.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
