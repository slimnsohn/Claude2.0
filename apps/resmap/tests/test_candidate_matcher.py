"""Tests for the cross-venue candidate matcher.

Scoring/date logic is unit-tested; find_candidates runs against resmap_test
with seeded markets (integration).
"""
from datetime import datetime, timedelta, timezone

import pytest

from ingest.core import MarketRecord, ingest
from parse.candidate_matcher import (_dates_compatible, _score_titles,
                                     find_candidates)

NOW = datetime(2026, 6, 12, tzinfo=timezone.utc)


# ── unit: scoring + date window ──────────────────────────────────────────────

def test_score_titles_paraphrase_high():
    a = "Will France win the 2026 FIFA World Cup?"
    b = "France wins 2026 World Cup (FIFA)?"
    assert _score_titles(a, b) > 0.65


def test_score_titles_unrelated_low():
    a = "Will France win the 2026 FIFA World Cup?"
    b = "Fed cuts rates in September 2026?"
    assert _score_titles(a, b) < 0.5


def test_dates_compatible_within_window():
    assert _dates_compatible(NOW, NOW + timedelta(days=6), window_days=7)


def test_dates_outside_window():
    assert not _dates_compatible(NOW, NOW + timedelta(days=8), window_days=7)


def test_dates_missing_treated_compatible():
    # missing closes_at must not exclude a market — over-recall is fine,
    # missing a real pair is the costly error
    assert _dates_compatible(None, NOW, window_days=7)
    assert _dates_compatible(None, None, window_days=7)


# ── integration: find_candidates against seeded DB ───────────────────────────

def _mk(venue, vid, title, closes_at=NOW, status="open"):
    return MarketRecord(venue_code=venue, venue_market_id=vid, title=title,
                        raw_rules="r", closes_at=closes_at, status=status)


@pytest.mark.integration
def test_find_candidates_surfaces_same_event_pair(db_conn):
    ingest(db_conn, [
        _mk("polymarket", "0xWC", "Will France win the 2026 FIFA World Cup?"),
        _mk("kalshi", "KXWC-FR", "France wins the 2026 World Cup?"),
        _mk("kalshi", "KXCPI", "CPI above 3% in June 2026?"),
    ])
    pairs = find_candidates(db_conn, min_similarity=0.65)
    assert len(pairs) == 1
    pair = pairs[0]
    assert pair.title_a.startswith("Will France")
    assert pair.title_b.startswith("France wins")
    assert pair.similarity > 0.65


@pytest.mark.integration
def test_find_candidates_date_window_excludes(db_conn):
    ingest(db_conn, [
        _mk("polymarket", "0xA", "Will France win the 2026 FIFA World Cup?",
            closes_at=NOW),
        _mk("kalshi", "KXA", "France wins the 2026 World Cup?",
            closes_at=NOW + timedelta(days=30)),
    ])
    assert find_candidates(db_conn, min_similarity=0.65,
                           date_window_days=7) == []


@pytest.mark.integration
def test_find_candidates_ignores_closed_markets(db_conn):
    ingest(db_conn, [
        _mk("polymarket", "0xA", "Will France win the 2026 FIFA World Cup?"),
        _mk("kalshi", "KXA", "France wins the 2026 World Cup?", status="closed"),
    ])
    assert find_candidates(db_conn) == []


@pytest.mark.integration
def test_find_candidates_never_pairs_within_one_venue(db_conn):
    ingest(db_conn, [
        _mk("polymarket", "0xA", "Will France win the 2026 FIFA World Cup?"),
        _mk("polymarket", "0xB", "Will France win the 2026 World Cup (FIFA)?"),
    ])
    assert find_candidates(db_conn) == []


@pytest.mark.integration
def test_find_candidates_sorted_by_similarity_desc(db_conn):
    ingest(db_conn, [
        _mk("polymarket", "0xA", "Will France win the 2026 FIFA World Cup?"),
        _mk("kalshi", "KX1", "France wins the 2026 World Cup?"),
        _mk("kalshi", "KX2", "Will France win the 2026 FIFA World Cup?"),
    ])
    pairs = find_candidates(db_conn, min_similarity=0.6)
    assert len(pairs) == 2
    assert pairs[0].similarity >= pairs[1].similarity
    assert pairs[0].similarity == pytest.approx(1.0)
