"""Consensus aggregation across multiple books, on the de-vigged probability scale."""
from __future__ import annotations
from datetime import datetime, timedelta
from typing import Iterable
from core.types import BookOdds
from core.vig import devig_two_way_shin


def normalize_weights(weights: dict[str, float], present: Iterable[str]) -> dict[str, float]:
    present_set = set(present)
    sub = {b: w for b, w in weights.items() if b in present_set and w > 0}
    total = sum(sub.values())
    if total <= 0:
        return {}
    return {b: w / total for b, w in sub.items()}


def weighted_consensus(
    over_lines: list[BookOdds],
    under_lines: list[BookOdds],
    weights: dict[str, float],
    staleness_seconds: int,
    snapshot_time: datetime,
    min_books: int = 1,
) -> tuple[float, list[str]]:
    """Return (consensus_prob_over, books_actually_used).

    Pairs over/under lines per book, de-vigs via Shin, weights by configured
    book weight, drops books with stale fetches or only one side present.
    Raises ValueError if no fresh books or fewer than `min_books` qualify.
    """
    cutoff = snapshot_time - timedelta(seconds=staleness_seconds)

    by_book_over = {bl.book: bl for bl in over_lines if bl.fetched_at >= cutoff}
    by_book_under = {bl.book: bl for bl in under_lines if bl.fetched_at >= cutoff}
    common_books = sorted(set(by_book_over.keys()) & set(by_book_under.keys()))

    if not common_books:
        raise ValueError("No fresh books with both sides present for consensus")

    if len(common_books) < min_books:
        raise ValueError(f"Need at least {min_books} books, found {len(common_books)}")

    norm_weights = normalize_weights(weights, common_books)
    if not norm_weights:
        raise ValueError("No configured-weighted books among present set")

    consensus = 0.0
    used = []
    for book in common_books:
        if book not in norm_weights:
            continue
        fair_over, _ = devig_two_way_shin(
            by_book_over[book].american_odds,
            by_book_under[book].american_odds,
        )
        consensus += norm_weights[book] * fair_over
        used.append(book)

    return consensus, used
