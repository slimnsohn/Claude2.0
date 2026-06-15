#!/usr/bin/env python
"""Live draft-day assistant.

Tracks your draft pick-by-pick and tells you the best available player — by
projected next-season value, or weighted to your roster's category needs.

Start:   python livedraft.py            # uses projected value, optional --punt
Commands (type at the > prompt):
    <name>          a player was drafted (by anyone)   e.g.  "jokic"
    me <name>       YOU drafted this player            e.g.  "me wembanyama"
    best [N]        show best available by value
    need [N]        show best available for YOUR needs
    roster          your picks + category profile
    undo            undo the last pick
    help / quit
"""

import argparse
import os
import sys

from fbball import db, livedraft, recommend, valuation

DEFAULT_DB = os.path.join(os.path.dirname(__file__), "data", "fbball.duckdb")
CATS = valuation.CATS


def _row(p, extra=""):
    z = "".join(f"{p['zscores'][c]:>5.1f}" for c in CATS)
    return f"  {p['full_name'][:22]:<22} {z}  {p['total_value']:>6.1f}{extra}"


def _print_best(draft, n):
    print(f"\n  {'BEST AVAILABLE':<22} " + "".join(f"{valuation.CAT_DISPLAY[c]:>5}" for c in CATS) + "   TOT")
    for p in draft.best(n):
        print(_row(p))


def _print_need(draft, n):
    if not draft.my_players():
        print("  (draft some players to 'me' first, then needs kick in)")
        return _print_best(draft, n)
    print(f"\n  {'FOR YOUR NEEDS':<22} " + "".join(f"{valuation.CAT_DISPLAY[c]:>5}" for c in CATS) + "   TOT   FIT")
    for p in draft.by_need(n):
        print(_row(p, f" {p['needs_value']:>5.1f}"))


def _print_roster(draft):
    mine = draft.my_players()
    if not mine:
        print("  (no picks yet)")
        return
    print("\n  YOUR ROSTER:")
    for p in mine:
        print(_row(p))
    profile = recommend.category_profile(mine)
    weak = sorted(CATS, key=lambda c: profile[c])[:3]
    print("  weakest cats:", ", ".join(f"{valuation.CAT_DISPLAY[c]}({profile[c]:+.1f})" for c in weak))


def main(argv=None):
    p = argparse.ArgumentParser(description="live draft assistant")
    p.add_argument("--db", default=DEFAULT_DB)
    p.add_argument("--punt", nargs="*", default=[], metavar="CAT")
    p.add_argument("--min-gp", type=int, default=25)
    args = p.parse_args(argv)
    punt = set(args.punt)

    con = db.connect(args.db)
    try:
        ranked = valuation.rank_from_db(con, source="projection", punt=punt,
                                        min_gp=args.min_gp)
    finally:
        con.close()
    if not ranked:
        sys.exit("No projections. Run:  python ingest.py prep   (needs game logs + ages)")

    draft = livedraft.LiveDraft(ranked)
    punt_note = f"  (punt: {', '.join(valuation.CAT_DISPLAY[c] for c in punt)})" if punt else ""
    print(f"Live draft — {len(ranked)} projected players ranked.{punt_note}")
    print("Type a name as players are picked. 'me <name>' for your picks. 'help' for commands.")
    _print_best(draft, 10)

    while True:
        try:
            line = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            continue
        parts = line.split(maxsplit=1)
        cmd, rest = parts[0].lower(), (parts[1] if len(parts) > 1 else "")

        if cmd in ("quit", "exit", "q"):
            break
        if cmd in ("help", "h", "?"):
            print(__doc__)
            continue
        if cmd in ("best", "b"):
            _print_best(draft, int(rest) if rest.isdigit() else 15)
            continue
        if cmd in ("need", "n"):
            _print_need(draft, int(rest) if rest.isdigit() else 15)
            continue
        if cmd in ("roster", "r"):
            _print_roster(draft)
            continue
        if cmd in ("undo", "u"):
            pid = draft.undo()
            print(f"  undid: {draft.by_id[pid]['full_name']}" if pid else "  nothing to undo")
            continue

        mine = cmd in ("me", "my")
        name = rest if mine else line
        player = draft.resolve(name)
        if not player:
            print(f"  no match for {name!r} (try a fuller name)")
            continue
        if draft.draft(player["player_id"], mine=mine):
            tag = "YOU drafted" if mine else "off the board"
            print(f"  {tag}: {player['full_name']}")
            (_print_need if mine else _print_best)(draft, 8)
        else:
            print(f"  {player['full_name']} already drafted")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
