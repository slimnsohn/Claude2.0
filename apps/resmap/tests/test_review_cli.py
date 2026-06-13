"""Integration tests for the review CLI against resmap_test."""
from datetime import datetime, timezone

import pytest

from ingest.core import MarketRecord, ingest
from parse.review_cli import (_resolve_prefix, cmd_approve, cmd_list,
                              cmd_list_sources, cmd_merge_source, cmd_show)

pytestmark = pytest.mark.integration


def _mk_source(cur, name):
    cur.execute("INSERT INTO sources (canonical_name) VALUES (%s) RETURNING source_id",
                (name,))
    return cur.fetchone()[0]


def test_merge_source_sets_merged_into(db_conn):
    with db_conn.cursor() as cur:
        canon = _mk_source(cur, "FIFA")
        alias = _mk_source(cur, "Fifa official body")
    db_conn.commit()
    cmd_merge_source(db_conn, "Fifa official", "FIFA")
    with db_conn.cursor() as cur:
        cur.execute("SELECT merged_into FROM sources WHERE source_id=%s", (alias,))
        assert cur.fetchone()[0] == canon


def test_merge_source_rejects_self_merge(db_conn):
    with db_conn.cursor() as cur:
        _mk_source(cur, "FIFA")
    db_conn.commit()
    with pytest.raises(SystemExit, match="itself"):
        cmd_merge_source(db_conn, "FIFA", "FIFA")


def test_merge_source_rejects_noncanonical_target(db_conn):
    # target that is itself already an alias would create a 2-level chain
    with db_conn.cursor() as cur:
        canon = _mk_source(cur, "FIFA")
        mid = _mk_source(cur, "Fifa body")
        _mk_source(cur, "FIFA association")
        cur.execute("UPDATE sources SET merged_into=%s WHERE source_id=%s",
                    (canon, mid))
    db_conn.commit()
    with pytest.raises(SystemExit, match="canonical"):
        cmd_merge_source(db_conn, "FIFA association", "Fifa body")


def test_merge_source_rejects_alias_with_dependents(db_conn):
    # can't merge a row that other rows are already merged into (would chain)
    with db_conn.cursor() as cur:
        a = _mk_source(cur, "Authority A")
        b = _mk_source(cur, "Authority B")
        c = _mk_source(cur, "Authority C")
        cur.execute("UPDATE sources SET merged_into=%s WHERE source_id=%s", (b, c))
    db_conn.commit()
    with pytest.raises(SystemExit, match="dependent|merged into"):
        cmd_merge_source(db_conn, "Authority B", "Authority A")


def test_list_sources_shows_merge_status(db_conn, capsys):
    with db_conn.cursor() as cur:
        canon = _mk_source(cur, "FIFA")
        alias = _mk_source(cur, "Fifa official body")
        cur.execute("UPDATE sources SET merged_into=%s WHERE source_id=%s",
                    (canon, alias))
    db_conn.commit()
    cmd_list_sources(db_conn)
    out = capsys.readouterr().out
    assert "FIFA" in out
    assert "→" in out or "->" in out      # alias shown pointing at canonical


@pytest.fixture
def seeded_parse(db_conn):
    """One market with one unreviewed parse; returns its parsed_id."""
    ingest(db_conn, [MarketRecord(
        venue_code="polymarket", venue_market_id="0xREV1",
        title="Will X happen?", raw_rules="Resolves YES if X by 11:59pm ET.",
        status="open")])
    with db_conn.cursor() as cur:
        cur.execute("SELECT market_id, snapshot_id FROM rule_snapshots "
                    "JOIN markets USING (market_id)")
        market_id, snapshot_id = cur.fetchone()
        cur.execute("""
            INSERT INTO parsed_rules (market_id, snapshot_id, resolution_logic,
                threshold_def, confidence, extraction_method, reviewed, is_stale)
            VALUES (%s, %s, 'resolves YES if X', '>= 1', 0.8, 'llm', FALSE, FALSE)
            RETURNING parsed_id
        """, (market_id, snapshot_id))
        parsed_id = str(cur.fetchone()[0])
    db_conn.commit()
    return parsed_id


def test_list_shows_unreviewed(seeded_parse, db_conn, capsys):
    cmd_list(db_conn)
    out = capsys.readouterr().out
    assert seeded_parse[:8] in out
    assert "Will X happen?" in out


def test_show_displays_parse_beside_verbatim_rules(seeded_parse, db_conn, capsys):
    cmd_show(db_conn, seeded_parse[:8])
    out = capsys.readouterr().out
    assert "resolves YES if X" in out                  # parsed interpretation
    assert "Resolves YES if X by 11:59pm ET." in out   # verbatim source text


def test_approve_flips_reviewed_and_method(seeded_parse, db_conn, capsys):
    cmd_approve(db_conn, [seeded_parse[:8]])
    with db_conn.cursor() as cur:
        cur.execute("SELECT reviewed, extraction_method FROM parsed_rules")
        reviewed, method = cur.fetchone()
    assert reviewed is True
    assert method == "llm_reviewed"

    # and it leaves the review queue
    cmd_list(db_conn)
    assert seeded_parse[:8] not in capsys.readouterr().out.splitlines()[-1]


def test_resolve_prefix_rejects_unknown(seeded_parse, db_conn):
    with db_conn.cursor() as cur:
        with pytest.raises(SystemExit, match="no parse matches"):
            _resolve_prefix(cur, "ffffffff")


def test_list_empty_queue(db_conn, capsys):
    cmd_list(db_conn)
    assert "queue is clear" in capsys.readouterr().out
