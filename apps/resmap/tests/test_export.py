"""Integration tests for the Postgres → Parquet export (vs resmap_test)."""
import pyarrow.parquet as pq
import pytest

from export.to_parquet import export
from ingest.core import MarketRecord, ingest

pytestmark = pytest.mark.integration


def _seed(db_conn):
    """A small but representative slice: 2 markets (2 venues), a merged source,
    one parse, one equivalence, one rule-change."""
    ingest(db_conn, [
        MarketRecord(venue_code="polymarket", venue_market_id="0xA",
                     title="Will France win?", raw_rules="r", category="sports",
                     status="open"),
        MarketRecord(venue_code="kalshi", venue_market_id="KXB",
                     title="France wins?", raw_rules="r2", category="sports",
                     status="open"),
    ])
    with db_conn.cursor() as cur:
        cur.execute("SELECT m.market_id, v.code, s.snapshot_id FROM markets m "
                    "JOIN venues v USING(venue_id) JOIN rule_snapshots s USING(market_id)")
        rows = {code: (mid, snap) for mid, code, snap in cur.fetchall()}
        # canonical + alias merged into it
        cur.execute("INSERT INTO sources (canonical_name) VALUES ('FIFA') RETURNING source_id")
        canon = cur.fetchone()[0]
        cur.execute("INSERT INTO sources (canonical_name, merged_into) "
                    "VALUES ('Fifa official body', %s) RETURNING source_id", (canon,))
        alias = cur.fetchone()[0]
        # parse on the polymarket market points at the ALIAS source
        pa_mid, pa_snap = rows["polymarket"]
        cur.execute("""INSERT INTO parsed_rules (market_id, snapshot_id, source_id,
            resolution_logic, threshold_def, confidence, extraction_method,
            reviewed, is_stale)
            VALUES (%s,%s,%s,'resolves YES if France wins','outright',0.9,'llm',TRUE,FALSE)""",
            (pa_mid, pa_snap, alias))
        cur.execute("""INSERT INTO equivalences (market_a_id, market_b_id,
            match_type, divergence_axes, divergence_notes, risk_score)
            VALUES (%s,%s,'false_friend',ARRAY['source','cutoff'],'note',0.7)""",
            (rows["polymarket"][0], rows["kalshi"][0]))
        kx_mid, kx_snap = rows["kalshi"]
        cur.execute("""INSERT INTO rule_snapshots (market_id, raw_rules, content_hash)
                       VALUES (%s,'edited','h9') RETURNING snapshot_id""", (kx_mid,))
        new_snap = cur.fetchone()[0]
        cur.execute("""INSERT INTO rule_change_events (market_id, prev_snapshot_id,
                       new_snapshot_id, severity) VALUES (%s,%s,%s,'unknown')""",
                    (kx_mid, kx_snap, new_snap))
    db_conn.commit()


def test_export_writes_all_layers_with_counts(db_conn, tmp_path):
    _seed(db_conn)
    stats = export(db_conn, str(tmp_path))
    assert stats["markets"] == 2
    assert stats["parsed_rules"] == 1
    assert stats["equivalences"] == 1
    assert stats["rule_changes"] == 1
    assert stats["sources"] == 2
    # every reported layer produced a readable parquet dataset
    for layer in ("markets", "parsed_rules", "equivalences", "rule_changes", "sources"):
        assert (tmp_path / layer).exists(), f"{layer} not written"


def test_markets_partitioned_by_venue(db_conn, tmp_path):
    _seed(db_conn)
    export(db_conn, str(tmp_path))
    parts = {p.name for p in (tmp_path / "markets").iterdir() if p.is_dir()}
    assert "venue=polymarket" in parts
    assert "venue=kalshi" in parts
    tbl = pq.read_table(tmp_path / "markets")
    assert tbl.num_rows == 2
    assert set(tbl.column("venue").to_pylist()) == {"polymarket", "kalshi"}


def test_parsed_rules_source_resolves_through_merged_into(db_conn, tmp_path):
    _seed(db_conn)
    export(db_conn, str(tmp_path))
    tbl = pq.read_table(tmp_path / "parsed_rules")
    # parse pointed at the alias, but the export records the canonical authority
    assert tbl.column("authoritative_source").to_pylist() == ["FIFA"]


def test_equivalences_divergence_axes_list_preserved(db_conn, tmp_path):
    _seed(db_conn)
    export(db_conn, str(tmp_path))
    tbl = pq.read_table(tmp_path / "equivalences")
    assert tbl.column("divergence_axes").to_pylist() == [["source", "cutoff"]]
    assert tbl.column("match_type").to_pylist() == ["false_friend"]


def test_export_empty_db_is_safe(db_conn, tmp_path):
    # no rows seeded — export must not crash, returns zero counts
    stats = export(db_conn, str(tmp_path))
    assert stats == {"markets": 0, "parsed_rules": 0, "equivalences": 0,
                     "rule_changes": 0, "sources": 0}
