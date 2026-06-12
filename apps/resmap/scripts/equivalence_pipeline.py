"""Staged equivalence pipeline. Matching the full registry takes minutes and
LLM parsing/judging takes ~30-45s per call, so the stages run separately with
the candidate pairs cached as JSON in between:

    python -m scripts.equivalence_pipeline match --out pairs.json --top 12
    # parse any venue_market_ids the match stage reported missing:
    python -m parse.rule_parser --ids ID [ID ...]
    python -m scripts.equivalence_pipeline compare --pairs pairs.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from dotenv import load_dotenv

from parse.candidate_matcher import CandidatePair, find_candidates
from parse.equivalence import run as equivalence_run


def get_conn():
    import psycopg
    return psycopg.connect(os.environ["DATABASE_URL"])


def _missing_parses(conn, pairs: list[CandidatePair]) -> list[str]:
    """venue_market_ids on either side of `pairs` lacking a fresh parse."""
    market_ids = sorted({m for p in pairs
                         for m in (p.market_a_id, p.market_b_id)})
    with conn.cursor() as cur:
        cur.execute("""
            SELECT m.venue_market_id
            FROM markets m
            WHERE m.market_id = ANY(%s::uuid[])
              AND NOT EXISTS (SELECT 1 FROM parsed_rules p
                              WHERE p.market_id = m.market_id
                                AND p.is_stale = FALSE)
        """, (market_ids,))
        return [r[0] for r in cur.fetchall()]


def cmd_match(conn, out: str, min_similarity: float, top: int) -> int:
    pairs = find_candidates(conn, min_similarity=min_similarity)
    selected = pairs[:top]
    with open(out, "w", encoding="utf-8") as f:
        json.dump([p.__dict__ for p in selected], f, indent=1)

    print(f"{len(pairs)} candidates >= {min_similarity}; "
          f"top {len(selected)} written to {out}")
    for p in selected:
        print(f"  {p.similarity:.2f}  {p.title_a[:50]:50} <-> {p.title_b[:50]}")

    missing = _missing_parses(conn, selected)
    if missing:
        print(f"\n{len(missing)} side(s) lack a fresh parse. Parse them with:")
        print(f"  python -m parse.rule_parser --ids {' '.join(missing)}")
    else:
        print("\nall sides parsed — ready for `compare`")
    return 0


def cmd_compare(conn, pairs_file: str) -> int:
    with open(pairs_file, encoding="utf-8") as f:
        pairs = [CandidatePair(**d) for d in json.load(f)]
    stats = equivalence_run(conn, pairs=pairs)
    print(f"[equivalence] {stats}")
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    load_dotenv()

    parser = argparse.ArgumentParser(description="staged equivalence pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    p_match = sub.add_parser("match")
    p_match.add_argument("--out", default="pairs.json")
    p_match.add_argument("--min-similarity", type=float, default=0.90)
    p_match.add_argument("--top", type=int, default=12)
    p_compare = sub.add_parser("compare")
    p_compare.add_argument("--pairs", default="pairs.json")
    args = parser.parse_args(argv)

    conn = get_conn()
    try:
        if args.command == "match":
            return cmd_match(conn, args.out, args.min_similarity, args.top)
        return cmd_compare(conn, args.pairs)
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
