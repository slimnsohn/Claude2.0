"""
Candidate matcher: surface likely same-event market pairs across Polymarket & Kalshi.

Cheap, high-recall first pass — a human (or the equivalence engine) confirms. Do NOT
try to be precise here; the equivalence engine does the careful semantic comparison.
Over-recall is fine; missing a real pair is the costly error.

Approach:
  - Filter to overlapping time windows + compatible categories.
  - Score title similarity (embeddings preferred over fuzzy string match for paraphrase).
  - Emit candidate (market_a_id, market_b_id, similarity) above a low threshold.

    python -m parse.candidate_matcher
"""
from __future__ import annotations


def find_candidates(conn, min_similarity: float = 0.7):
    """TODO: implement. Return list of (market_a_id, market_b_id, score).
    Suggestion: pull open markets per venue, embed titles, cosine-match across venues,
    constrain by closes_at proximity and category. Persist nothing here — hand pairs to
    the equivalence engine, which writes `equivalences` rows."""
    raise NotImplementedError("implement candidate cross-venue matching")
