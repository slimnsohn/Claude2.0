"""
Candidate matcher: surface likely same-event market pairs across Polymarket &
Kalshi.

Cheap, high-recall first pass — the equivalence engine (and ultimately a
human) confirms. Do NOT try to be precise here; over-recall is fine, missing
a real pair is the costly error. Persists nothing — pairs flow straight into
parse/equivalence.py, which writes `equivalences` rows.

Matching: rapidfuzz token_sort_ratio on titles (proven at 0.65 in the old
mismatch detector) + closes_at proximity blocking. Markets with no close date
are never excluded by the date filter (recall over precision). Swap in
embeddings later if fuzzy recall proves insufficient on paraphrased titles.

    python -m parse.candidate_matcher            # print candidate pairs
"""
from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from rapidfuzz import fuzz

DATE_WINDOW_DAYS = 7
MIN_SIMILARITY = 0.65


@dataclass
class CandidatePair:
    market_a_id: str          # polymarket side
    market_b_id: str          # kalshi side
    title_a: str
    title_b: str
    similarity: float


def _score_titles(a: str, b: str) -> float:
    return fuzz.token_sort_ratio(a, b) / 100.0


def _dates_compatible(a: Optional[datetime], b: Optional[datetime],
                      window_days: int = DATE_WINDOW_DAYS) -> bool:
    if a is None or b is None:
        return True  # unknown close date must not exclude a market
    return abs((a - b).days) <= window_days


def find_candidates(conn, min_similarity: float = MIN_SIMILARITY,
                    date_window_days: int = DATE_WINDOW_DAYS,
                    venue_a: str = "polymarket",
                    venue_b: str = "kalshi") -> list[CandidatePair]:
    """Cross-venue same-event candidates, sorted by similarity descending."""
    def open_markets(venue_code: str):
        # rules text required: a pair that can't be parsed can never be
        # equivalence-scored, and rules-less markets (Kalshi parlays) are
        # pure matching noise
        with conn.cursor() as cur:
            cur.execute("""
                SELECT m.market_id, m.title, m.closes_at
                FROM markets m JOIN venues v USING (venue_id)
                WHERE v.code = %s AND m.status = 'open'
                  AND EXISTS (SELECT 1 FROM rule_snapshots s
                              WHERE s.market_id = m.market_id
                                AND s.raw_rules <> '')
            """, (venue_code,))
            return cur.fetchall()

    side_a = open_markets(venue_a)
    side_b = open_markets(venue_b)

    pairs: list[CandidatePair] = []
    for a_id, a_title, a_closes in side_a:
        for b_id, b_title, b_closes in side_b:
            if not _dates_compatible(a_closes, b_closes, date_window_days):
                continue
            score = _score_titles(a_title, b_title)
            if score >= min_similarity:
                pairs.append(CandidatePair(str(a_id), str(b_id),
                                           a_title, b_title, score))

    pairs.sort(key=lambda p: p.similarity, reverse=True)
    return pairs


def main(argv: list[str] | None = None) -> int:
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    from dotenv import load_dotenv
    load_dotenv()

    parser = argparse.ArgumentParser(description="ResMap candidate matcher")
    parser.add_argument("--min-similarity", type=float, default=MIN_SIMILARITY)
    parser.add_argument("--date-window-days", type=int, default=DATE_WINDOW_DAYS)
    args = parser.parse_args(argv)

    import psycopg
    conn = psycopg.connect(os.environ["DATABASE_URL"])
    try:
        pairs = find_candidates(conn, args.min_similarity, args.date_window_days)
    finally:
        conn.close()

    for p in pairs:
        print(f"{p.similarity:.2f}  [poly] {p.title_a[:55]:55}  "
              f"[kalshi] {p.title_b[:55]}")
    print(f"\n{len(pairs)} candidate pair(s) "
          f"(min_similarity={args.min_similarity})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
