"""Integration tests for the ingest core against a real Postgres (resmap_test).

These prove the full TODO Phase 1 contract end-to-end with synthetic records
(no network): first run populates, identical re-run writes nothing, and a rule
edit produces a rule_change_events row and flips parsed_rules.is_stale.
"""
import pytest

from ingest.core import MarketRecord, ingest

pytestmark = pytest.mark.integration


def _record(rules: str = "Resolves YES if X happens by 11:59pm ET.",
            market_id: str = "0xTESTMARKET1") -> MarketRecord:
    return MarketRecord(
        venue_code="polymarket",
        venue_market_id=market_id,
        title="Will X happen?",
        raw_rules=rules,
        category="test",
        status="open",
        raw_payload={"volume": "12345.6"},
    )


def _one(cur, sql, params=()):
    cur.execute(sql, params)
    return cur.fetchone()


def test_first_ingest_populates(db_conn):
    stats = ingest(db_conn, [_record()])
    assert stats == {"new_markets": 1, "rule_changes": 0, "unchanged": 0}
    with db_conn.cursor() as cur:
        assert _one(cur, "SELECT count(*) FROM markets")[0] == 1
        assert _one(cur, "SELECT count(*) FROM rule_snapshots")[0] == 1
        assert _one(cur, "SELECT count(*) FROM rule_change_events")[0] == 0


def test_rerun_with_no_changes_is_idempotent(db_conn):
    ingest(db_conn, [_record()])
    stats = ingest(db_conn, [_record()])
    assert stats == {"new_markets": 0, "rule_changes": 0, "unchanged": 1}
    with db_conn.cursor() as cur:
        # the critical invariant: NO second snapshot for identical rules
        assert _one(cur, "SELECT count(*) FROM rule_snapshots")[0] == 1


def test_cosmetic_whitespace_churn_writes_no_snapshot(db_conn):
    ingest(db_conn, [_record("Resolves YES if X happens by 11:59pm ET.")])
    stats = ingest(db_conn, [_record("resolves yes  if X happens by 11:59pm ET. ")])
    assert stats["unchanged"] == 1
    with db_conn.cursor() as cur:
        assert _one(cur, "SELECT count(*) FROM rule_snapshots")[0] == 1


def test_rule_edit_creates_event_and_flags_stale_parses(db_conn):
    # v1 ingest
    ingest(db_conn, [_record("Resolves YES if X happens by 11:59pm ET.")])

    with db_conn.cursor() as cur:
        market_id, snap_v1 = _one(cur, """
            SELECT m.market_id, s.snapshot_id
            FROM markets m JOIN rule_snapshots s ON s.market_id = m.market_id
        """)
        # seed a parse against the v1 snapshot, as Phase 2 would
        cur.execute("""
            INSERT INTO parsed_rules (market_id, snapshot_id, resolution_logic,
                                      extraction_method, reviewed)
            VALUES (%s, %s, 'resolves YES if X', 'manual', TRUE)
        """, (market_id, snap_v1))
    db_conn.commit()

    # v2 ingest: the venue edited the cutoff — a material rule change
    stats = ingest(db_conn, [_record("Resolves YES if X happens by 6:00pm ET.")])
    assert stats == {"new_markets": 0, "rule_changes": 1, "unchanged": 0}

    with db_conn.cursor() as cur:
        # append-only history: both snapshots retained
        assert _one(cur, "SELECT count(*) FROM rule_snapshots")[0] == 2

        # the change event links the exact prev/new snapshots
        prev_id, new_id, severity = _one(cur, """
            SELECT prev_snapshot_id, new_snapshot_id, severity
            FROM rule_change_events
        """)
        assert prev_id == snap_v1
        assert new_id != snap_v1
        assert severity == "unknown"

        # existing parses flagged for re-parse
        assert _one(cur, "SELECT is_stale FROM parsed_rules")[0] is True


def test_new_market_vs_updated_market_counting(db_conn):
    ingest(db_conn, [_record(market_id="0xA"), _record(market_id="0xB")])
    stats = ingest(db_conn, [_record(market_id="0xB"),
                             _record(market_id="0xC")])
    assert stats["new_markets"] == 1   # only 0xC
    assert stats["unchanged"] == 1     # 0xB
    with db_conn.cursor() as cur:
        assert _one(cur, "SELECT count(*) FROM markets")[0] == 3


def test_unknown_venue_rejected(db_conn):
    rec = _record()
    rec.venue_code = "nonexistent"
    with pytest.raises(ValueError, match="unknown venue"):
        ingest(db_conn, [rec])
