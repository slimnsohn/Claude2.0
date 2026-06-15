#!/usr/bin/env python
"""Fantasy Basketball — draft board.

Punt-aware 9-cat value, grouped into tiers, with positional rank for scarcity.

Usage:
    python draft.py                       # full board, season value
    python draft.py --top 60
    python draft.py --punt FT_PCT TOV     # board for a punt build
    python draft.py --pos C               # only centers (positional run)
    python draft.py --gap 1.0             # coarser tiers (bigger gap to break)

Tiers break at value cliffs. 'Pos' shows positional rank (C3 = 3rd-best center).
"""

import argparse
import os
import sys

from fbball import db, draft as board, valuation

DEFAULT_DB = os.path.join(os.path.dirname(__file__), "data", "fbball.duckdb")
CATS = valuation.CATS


def main(argv=None):
    p = argparse.ArgumentParser(description="draft board")
    p.add_argument("--db", default=DEFAULT_DB)
    p.add_argument("--season", default="2025-26")
    p.add_argument("--source", choices=["season", "recent"], default="season")
    p.add_argument("--punt", nargs="*", default=[], metavar="CAT")
    p.add_argument("--pos", default=None, help="filter to an NBA position (G/F/C)")
    p.add_argument("--top", type=int, default=80)
    p.add_argument("--gap", type=float, default=0.75, help="tier-break value gap")
    p.add_argument("--min-gp", type=int, default=25)
    p.add_argument("--min-min", type=float, default=15.0)
    args = p.parse_args(argv)

    punt = set(args.punt)
    bad = punt - set(CATS)
    if bad:
        sys.exit(f"Unknown punt cat(s): {', '.join(bad)}. Choose from {', '.join(CATS)}")

    con = db.connect(args.db)
    try:
        players = board.build_board(
            con, season=args.season, source=args.source,
            min_gp=args.min_gp, min_min=args.min_min, punt=punt, gap=args.gap,
        )
    finally:
        con.close()

    if args.pos:
        players = [p for p in players
                   if board.primary_position(p.get("nba_position")) == args.pos]
    players = players[: args.top]

    label = f"{args.source} value, {args.season}"
    if punt:
        label += f"  |  PUNT: {', '.join(valuation.CAT_DISPLAY[c] for c in punt)}"
    if args.pos:
        label += f"  |  POS: {args.pos}"
    print(f"\nDRAFT BOARD — {label}\n")

    header = (f"{'Rk':>3} {'Tier':>4} {'Player':<22} {'Pos':>4} {'GP':>3} "
              + "".join(f"{valuation.CAT_DISPLAY[c]:>6}" for c in CATS)
              + f" {'TOTAL':>7}")
    print(header)
    print("-" * len(header))

    last_tier = None
    for p in players:
        if p["tier"] != last_tier:
            print(f"{'':>3} {'':>4} ── Tier {p['tier']} " + "─" * 20)
            last_tier = p["tier"]
        line = (f"{p['rank']:>3} {p['tier']:>4} {p['full_name'][:22]:<22} "
                f"{p['pos_rank']:>4} {int(p['gp'] or 0):>3} "
                + "".join(f"{p['zscores'][c]:>6.2f}" for c in CATS)
                + f" {p['total_value']:>7.2f}")
        print(line)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
