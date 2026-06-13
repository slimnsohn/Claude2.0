"""
Bootstrap the source-merge curation (Layer 2): ask Claude to cluster the
canonical `sources` rows into groups that name the SAME real-world authority,
then print the `review_cli merge-source` commands a human runs to apply them.

It NEVER merges automatically — the human approval is the moat. Output is a
proposal; the curator decides.

    python -m scripts.cluster_sources                 # propose merges
    python -m scripts.cluster_sources --apply         # run the merges (still
                                                      #   one transaction; review first)
"""
from __future__ import annotations

import argparse
import json
import os
import sys

CLUSTER_PROMPT = """You are de-duplicating a registry of prediction-market \
settlement authorities. Group ONLY names that denote the SAME real-world \
authority (e.g. "FIFA" and "Fifa official body"; "NASA GISS LOTI" and "NASA \
Goddard land-ocean index"). Do NOT group merely related authorities (e.g. \
"AP" and "Reuters" are different; "NBA" and "ESPN" are different). For each \
group pick the shortest clear name as the canonical. Return ONLY a JSON object: \
{"groups": [{"canonical": "<name>", "aliases": ["<name>", ...]}, ...]}. Omit \
singletons. Every name you output must be copied verbatim from the input list.

SOURCE NAMES:
"""


def propose_merges(names: list[str], judge=None) -> list[dict]:
    """Return [{canonical, aliases:[...]}], validated so every name is real
    and each alias appears in at most one group."""
    judge = judge or _default_judge
    raw = judge(CLUSTER_PROMPT + "\n".join(f"- {n}" for n in names))
    valid = set(names)
    groups, claimed = [], set()
    for g in raw.get("groups", []):
        canon = g.get("canonical")
        aliases = [a for a in g.get("aliases", [])
                   if a in valid and a != canon and a not in claimed]
        if canon in valid and aliases:
            groups.append({"canonical": canon, "aliases": aliases})
            claimed.update(aliases)
    return groups


def format_commands(groups: list[dict]) -> list[str]:
    cmds = []
    for g in groups:
        for alias in g["aliases"]:
            cmds.append(f'python -m parse.review_cli merge-source "{alias}" "{g["canonical"]}"')
    return cmds


def _default_judge(prompt: str) -> dict:
    from parse.claude_cli import call_claude_json
    return call_claude_json(prompt)


def _canonical_names(conn) -> list[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT canonical_name FROM sources WHERE merged_into IS NULL "
                    "ORDER BY canonical_name")
        return [r[0] for r in cur.fetchall()]


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    from dotenv import load_dotenv
    load_dotenv()
    parser = argparse.ArgumentParser(description="propose source merges (claude)")
    parser.add_argument("--apply", action="store_true",
                        help="run the proposed merges (review the proposal first)")
    args = parser.parse_args(argv)

    import psycopg
    from parse.review_cli import cmd_merge_source
    conn = psycopg.connect(os.environ["DATABASE_URL"])
    try:
        names = _canonical_names(conn)
        groups = propose_merges(names)
        if not groups:
            print("no near-duplicate authorities proposed")
            return 0
        for g in groups:
            print(f"\ncanonical: {g['canonical']}")
            for a in g["aliases"]:
                print(f"    alias: {a}")
        print("\n" + "\n".join(format_commands(groups)))
        if args.apply:
            print("\napplying...")
            for g in groups:
                for alias in g["aliases"]:
                    try:
                        cmd_merge_source(conn, alias, g["canonical"])
                    except SystemExit as e:
                        print(f"  skipped {alias!r}: {e}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
