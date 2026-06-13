"""Tests for the equivalence engine (the crown jewel).

compare() is unit-tested with a fake judge — deterministic axes must never
invoke the LLM. run() is integration-tested against resmap_test.
"""
from datetime import datetime, timezone

import pytest

from ingest.core import MarketRecord, ingest
from parse.equivalence import AXIS_WEIGHTS, compare, run

CUTOFF = datetime(2026, 11, 4, 5, 0, tzinfo=timezone.utc)


def _parsed(source_id="S1", cutoff_time=CUTOFF, cutoff_basis="event_time",
            tie_handling="resolves NO on tie", threshold_def=">= 270 votes",
            source_name="AP race call", resolution_logic="resolves YES if X"):
    return {
        "source_id": source_id, "source_name": source_name,
        "cutoff_time": cutoff_time, "cutoff_basis": cutoff_basis,
        "tie_handling": tie_handling, "threshold_def": threshold_def,
        "resolution_logic": resolution_logic,
    }


class FakeJudge:
    """Records calls; returns a configured set of differing axes."""
    def __init__(self, axes_different=(), notes="judged"):
        self.axes_different = list(axes_different)
        self.notes = notes
        self.calls = []

    def __call__(self, parsed_a, parsed_b, axes):
        self.calls.append(list(axes))
        return {"axes_different": [a for a in self.axes_different if a in axes],
                "notes": self.notes}


# ── compare(): deterministic paths ───────────────────────────────────────────

def test_identical_parses_true_match_without_judge():
    judge = FakeJudge()
    result = compare(_parsed(), _parsed(), judge=judge)
    assert result["match_type"] == "true_match"
    assert result["risk_score"] == 0.0
    assert result["divergence_axes"] == []
    assert judge.calls == []  # everything resolved deterministically


def test_different_source_ids_is_false_friend():
    judge = FakeJudge()
    result = compare(_parsed(source_id="S1"), _parsed(source_id="S2"),
                     judge=judge)
    assert "source" in result["divergence_axes"]
    assert result["risk_score"] >= AXIS_WEIGHTS["source"]
    assert result["match_type"] == "false_friend"
    assert judge.calls == []


def test_different_cutoff_times_detected_deterministically():
    other = datetime(2026, 11, 3, 23, 0, tzinfo=timezone.utc)
    result = compare(_parsed(), _parsed(cutoff_time=other), judge=FakeJudge())
    assert "cutoff" in result["divergence_axes"]
    assert result["match_type"] == "near_match"   # 0.25 == near/false boundary
    assert result["risk_score"] == pytest.approx(0.25)


def test_text_axis_normalization_avoids_judge():
    a = _parsed(tie_handling="Resolves NO on tie.")
    b = _parsed(tie_handling="resolves no on tie")
    judge = FakeJudge()
    result = compare(a, b, judge=judge)
    assert result["match_type"] == "true_match"
    assert judge.calls == []


def test_ambiguous_tie_text_goes_to_judge_only_that_axis():
    a = _parsed(tie_handling="ties go to NO")
    b = _parsed(tie_handling="resolves NO on a draw")
    judge = FakeJudge(axes_different=[])  # judge says semantically same
    result = compare(a, b, judge=judge)
    assert judge.calls == [["tie"]]
    assert result["match_type"] == "true_match"


def test_judge_confirms_tie_divergence_near_match():
    a = _parsed(tie_handling="ties resolve NO")
    b = _parsed(tie_handling="ties void the market")
    judge = FakeJudge(axes_different=["tie"], notes="void vs NO on draw")
    result = compare(a, b, judge=judge)
    assert result["divergence_axes"] == ["tie"]
    assert result["risk_score"] == pytest.approx(AXIS_WEIGHTS["tie"])
    assert result["match_type"] == "near_match"
    assert "void vs NO" in result["divergence_notes"]


def test_tie_plus_threshold_crosses_into_false_friend():
    a = _parsed(tie_handling="ties resolve NO", threshold_def="> 50%")
    b = _parsed(tie_handling="ties void", threshold_def=">= 50.0%")
    judge = FakeJudge(axes_different=["tie", "threshold"])
    result = compare(a, b, judge=judge)
    assert result["risk_score"] == pytest.approx(0.30)
    assert result["match_type"] == "false_friend"


def test_both_axes_null_is_same():
    a = _parsed(tie_handling=None, threshold_def=None)
    b = _parsed(tie_handling=None, threshold_def=None)
    judge = FakeJudge()
    result = compare(a, b, judge=judge)
    assert result["match_type"] == "true_match"
    assert judge.calls == []


def test_one_side_missing_source_goes_to_judge():
    a = _parsed(source_id=None, source_name="official FIFA information")
    b = _parsed(source_id="S2", source_name="FIFA official info")
    judge = FakeJudge(axes_different=[])
    result = compare(a, b, judge=judge)
    assert "source" in judge.calls[0]
    assert result["match_type"] == "true_match"


# ── run(): persistence (integration) ─────────────────────────────────────────

def _seed_pair(db_conn, source_b="AP race call"):
    """Two cross-venue markets with fresh parses sharing/differing sources."""
    ingest(db_conn, [
        MarketRecord(venue_code="polymarket", venue_market_id="0xE1",
                     title="Will France win the 2026 FIFA World Cup?",
                     raw_rules="r1", status="open"),
        MarketRecord(venue_code="kalshi", venue_market_id="KXE1",
                     title="France wins the 2026 World Cup?",
                     raw_rules="r2", status="open"),
    ])
    with db_conn.cursor() as cur:
        cur.execute("""
            SELECT m.market_id, s.snapshot_id, v.code
            FROM markets m
            JOIN rule_snapshots s USING (market_id)
            JOIN venues v USING (venue_id)
        """)
        rows = cur.fetchall()
        for market_id, snapshot_id, venue in rows:
            source = "AP race call" if venue == "polymarket" else source_b
            cur.execute("""
                INSERT INTO sources (canonical_name) VALUES (%s)
                ON CONFLICT (canonical_name) DO UPDATE SET canonical_name=EXCLUDED.canonical_name
                RETURNING source_id
            """, (source,))
            source_id = cur.fetchone()[0]
            cur.execute("""
                INSERT INTO parsed_rules (market_id, snapshot_id, source_id,
                    resolution_logic, tie_handling, threshold_def,
                    extraction_method, reviewed, is_stale)
                VALUES (%s,%s,%s,'resolves YES if France wins',
                        'standard', 'outright winner', 'llm', FALSE, FALSE)
            """, (market_id, snapshot_id, source_id))
    db_conn.commit()


@pytest.mark.integration
def test_merged_into_resolves_source_axis(db_conn):
    """Layer 2: two distinct source rows that name the same authority fire the
    source axis until a curator merges one into the other; then it clears."""
    _seed_pair(db_conn, source_b="AP race call (alt wording)")  # poly="AP race call"
    run(db_conn, judge=FakeJudge(), min_similarity=0.6)
    with db_conn.cursor() as cur:
        cur.execute("SELECT divergence_axes FROM equivalences")
        assert "source" in cur.fetchone()[0]   # distinct rows → fires

        cur.execute("SELECT source_id, canonical_name FROM sources")
        by_name = {name: sid for sid, name in cur.fetchall()}
        cur.execute("UPDATE sources SET merged_into = %s WHERE source_id = %s",
                    (by_name["AP race call"], by_name["AP race call (alt wording)"]))
    db_conn.commit()

    run(db_conn, judge=FakeJudge(), min_similarity=0.6)
    with db_conn.cursor() as cur:
        cur.execute("SELECT divergence_axes, match_type FROM equivalences")
        axes, match_type = cur.fetchone()
    assert "source" not in axes        # both resolve to the canonical authority
    assert match_type == "true_match"


@pytest.mark.integration
def test_run_persists_true_match(db_conn):
    _seed_pair(db_conn, source_b="AP race call")  # same source both sides
    stats = run(db_conn, judge=FakeJudge(), min_similarity=0.6)
    assert stats["compared"] == 1

    with db_conn.cursor() as cur:
        cur.execute("""SELECT match_type, risk_score, divergence_axes,
                              detected_by FROM equivalences""")
        match_type, risk, axes, detected_by = cur.fetchone()
    assert match_type == "true_match"
    assert risk == 0.0
    assert axes == []
    assert detected_by == "auto"


@pytest.mark.integration
def test_run_accepts_precomputed_pairs_without_matching(db_conn):
    """The staged pipeline passes cached CandidatePairs straight to run(),
    skipping the (slow) full-registry match."""
    from parse.candidate_matcher import CandidatePair
    _seed_pair(db_conn, source_b="AP race call")
    with db_conn.cursor() as cur:
        cur.execute("""
            SELECT m.market_id, v.code FROM markets m JOIN venues v USING (venue_id)
        """)
        by_venue = {code: str(mid) for mid, code in cur.fetchall()}
    pair = CandidatePair(by_venue["polymarket"], by_venue["kalshi"],
                         "France?", "France?", 0.99)
    stats = run(db_conn, judge=FakeJudge(), pairs=[pair])
    assert stats == {"candidates": 1, "compared": 1, "skipped_unparsed": 0}
    with db_conn.cursor() as cur:
        cur.execute("SELECT match_type FROM equivalences")
        assert cur.fetchone()[0] == "true_match"


@pytest.mark.integration
def test_run_persists_false_friend_on_source_divergence(db_conn):
    _seed_pair(db_conn, source_b="FIFA official feed")  # different source
    run(db_conn, judge=FakeJudge(), min_similarity=0.6)
    with db_conn.cursor() as cur:
        cur.execute("SELECT match_type, divergence_axes FROM equivalences")
        match_type, axes = cur.fetchone()
    assert match_type == "false_friend"
    assert "source" in axes


@pytest.mark.integration
def test_run_upserts_one_row_on_rerun(db_conn):
    _seed_pair(db_conn)
    run(db_conn, judge=FakeJudge(), min_similarity=0.6)
    run(db_conn, judge=FakeJudge(), min_similarity=0.6)
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*), max(updated_at) >= max(created_at) "
                    "FROM equivalences")
        count, updated_ok = cur.fetchone()
    assert count == 1
    assert updated_ok is True


@pytest.mark.integration
def test_run_skips_pairs_without_parses(db_conn):
    ingest(db_conn, [
        MarketRecord(venue_code="polymarket", venue_market_id="0xN1",
                     title="Will France win the 2026 FIFA World Cup?",
                     raw_rules="r", status="open"),
        MarketRecord(venue_code="kalshi", venue_market_id="KXN1",
                     title="France wins the 2026 World Cup?",
                     raw_rules="r", status="open"),
    ])  # no parsed_rules seeded
    stats = run(db_conn, judge=FakeJudge(), min_similarity=0.6)
    assert stats["compared"] == 0
    assert stats["skipped_unparsed"] == 1
