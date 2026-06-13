from datetime import datetime, timedelta
import pytest
from core.types import BookOdds
from core.consensus import weighted_consensus, normalize_weights


def _make_pair(book, over_odds, under_odds, age_seconds=0):
    now = datetime(2026, 5, 19, 18, 0)
    t = now - timedelta(seconds=age_seconds)
    return (BookOdds(book=book, american_odds=over_odds, fetched_at=t),
            BookOdds(book=book, american_odds=under_odds, fetched_at=t))


def test_normalize_weights_drops_absent():
    weights = {"pinnacle": 0.5, "fanduel": 0.25, "bookmaker": 0.15, "betonline": 0.10}
    present = {"fanduel", "bookmaker"}
    out = normalize_weights(weights, present)
    assert abs(sum(out.values()) - 1.0) < 1e-9
    assert abs(out["fanduel"] / out["bookmaker"] - 0.25 / 0.15) < 1e-6


def test_weighted_consensus_single_book_returns_book_prob():
    pin_over, pin_under = _make_pair("pinnacle", -110, -110)
    consensus, books_used = weighted_consensus(
        [pin_over], [pin_under],
        weights={"pinnacle": 1.0},
        staleness_seconds=600,
        snapshot_time=datetime(2026, 5, 19, 18, 0),
    )
    assert abs(consensus - 0.5) < 1e-4
    assert books_used == ["pinnacle"]


def test_weighted_consensus_two_books_weighted():
    p_over, p_under = _make_pair("pinnacle", -110, -110)
    f_over, f_under = _make_pair("fanduel", -120, 100)
    consensus, books = weighted_consensus(
        [p_over, f_over], [p_under, f_under],
        weights={"pinnacle": 0.5, "fanduel": 0.5},
        staleness_seconds=600,
        snapshot_time=datetime(2026, 5, 19, 18, 0),
    )
    assert 0.49 < consensus < 0.54
    assert sorted(books) == ["fanduel", "pinnacle"]


def test_weighted_consensus_drops_stale_books():
    fresh_over, fresh_under = _make_pair("pinnacle", -110, -110, age_seconds=60)
    stale_over, stale_under = _make_pair("fanduel", +500, -1000, age_seconds=900)
    consensus, books = weighted_consensus(
        [fresh_over, stale_over], [fresh_under, stale_under],
        weights={"pinnacle": 0.5, "fanduel": 0.5},
        staleness_seconds=600,
        snapshot_time=datetime(2026, 5, 19, 18, 0),
    )
    assert books == ["pinnacle"]
    assert abs(consensus - 0.5) < 1e-4


def test_weighted_consensus_raises_when_no_present_books():
    stale_over, stale_under = _make_pair("fanduel", -110, -110, age_seconds=900)
    with pytest.raises(ValueError, match="No fresh books"):
        weighted_consensus(
            [stale_over], [stale_under],
            weights={"pinnacle": 1.0, "fanduel": 1.0},
            staleness_seconds=600,
            snapshot_time=datetime(2026, 5, 19, 18, 0),
        )


def test_weighted_consensus_min_books_constraint():
    p_over, p_under = _make_pair("pinnacle", -110, -110)
    with pytest.raises(ValueError, match="Need at least"):
        weighted_consensus(
            [p_over], [p_under],
            weights={"pinnacle": 1.0},
            staleness_seconds=600,
            snapshot_time=datetime(2026, 5, 19, 18, 0),
            min_books=2,
        )
