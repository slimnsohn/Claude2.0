#!/usr/bin/env python
"""Fantasy Basketball — waiver pickup recommendations.

Ranks free agents by MARGINAL value to your roster's category needs, not raw
value. A player who fills a cat you're weak in beats a higher-raw-value player
who piles onto a cat you're already winning.

Usage:
    python ingest.py freeagents     # first: pull the FA pool (once a day)
    python waivers.py               # then: ranked pickups for your needs
    python waivers.py --punt FT_PCT TOV
    python waivers.py --source recent --top 25

Needs weighting: your weakest category gets weight 1.0, strongest 0.0.
"""

import argparse
import os
import sys

from fbball import db, recommend, valuation

DEFAULT_DB = os.path.join(os.path.dirname(__file__), "data", "fbball.duckdb")
CATS = valuation.CATS


def _fmt_profile(profile, weights):
    print("Your category profile (z-total across your roster) — high = strong:")
    ordered = sorted(CATS, key=lambda c: profile[c])  # weakest first
    parts = []
    for c in ordered:
        tag = "  <-- need" if weights[c] >= 0.66 and weights[c] > 0 else ""
        parts.append(f"  {valuation.CAT_DISPLAY[c]:>4}: {profile[c]:+6.1f}{tag}")
    print("\n".join(parts))


def main(argv=None):
    p = argparse.ArgumentParser(description="waiver pickup recommendations")
    p.add_argument("--db", default=DEFAULT_DB)
    p.add_argument("--season", default="2025-26")
    p.add_argument("--source", choices=["season", "recent"], default="season")
    p.add_argument("--punt", nargs="*", default=[], metavar="CAT")
    p.add_argument("--top", type=int, default=20)
    p.add_argument("--min-gp", type=int, default=20)
    p.add_argument("--min-min", type=float, default=10.0)
    args = p.parse_args(argv)

    punt = set(args.punt)
    bad = punt - set(CATS)
    if bad:
        sys.exit(f"Unknown punt cat(s): {', '.join(bad)}. Choose from {', '.join(CATS)}")

    con = db.connect(args.db)
    try:
        if db.count_free_agents(con) == 0:
            sys.exit("No free agents stored. Run:  python ingest.py freeagents")
        out = recommend.recommend_waivers(
            con, season=args.season, source=args.source,
            min_gp=args.min_gp, min_min=args.min_min, punt=punt, top=args.top,
        )
    finally:
        con.close()

    label = f"{args.source} value, {args.season}"
    if punt:
        label += f"  |  PUNT: {', '.join(valuation.CAT_DISPLAY[c] for c in punt)}"
    print(f"\nWAIVER PICKUPS — ranked by fit to YOUR needs ({label})")
    print(f"Free-agent pool valued: {out['pool']}\n")
    _fmt_profile(out["profile"], out["weights"])

    print(f"\n{'Rk':>3} {'Player':<22} {'Elig':<14} {'St':<4} "
          + "".join(f"{valuation.CAT_DISPLAY[c]:>6}" for c in CATS)
          + f" {'RAW':>6} {'FIT':>6}")
    print("-" * 120)
    for r in out["recommendations"]:
        elig = (r.get("eligible_positions") or "")[:13]
        st = (r.get("status") or "")[:3]
        line = f"{r['rank']:>3} {r['full_name'][:22]:<22} {elig:<14} {st:<4} "
        line += "".join(f"{r['zscores'][c]:>6.2f}" for c in CATS)
        line += f" {r['total_value']:>6.2f} {r['needs_value']:>6.2f}"
        print(line)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
