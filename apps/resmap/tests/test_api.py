"""Integration tests for the read-only API (FastAPI TestClient vs resmap_test)."""
import os

import pytest

pytestmark = pytest.mark.integration

TEST_DSN = os.environ.get("TEST_DATABASE_URL")


@pytest.fixture
def client(db_conn):
    """TestClient with get_db pointed at resmap_test, a fresh rate limiter, and
    two seeded keys (normal + tight rate limit). db_conn has already truncated
    the data tables for this test."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from tool.api.main import _rate_limiter, app, get_db

    from tool.api.auth import hash_key
    with db_conn.cursor() as cur:
        cur.execute("""
            INSERT INTO api_keys (key_hash, label, rate_per_min) VALUES
                (%s, 'test', 1000), (%s, 'ratelimited', 2)
            ON CONFLICT (key_hash) DO UPDATE SET active=TRUE, rate_per_min=EXCLUDED.rate_per_min
        """, (hash_key("testkey"), hash_key("rlkey")))
    db_conn.commit()

    import psycopg

    def _test_db():
        conn = psycopg.connect(TEST_DSN)
        try:
            yield conn
        finally:
            conn.close()

    app.dependency_overrides[get_db] = _test_db
    _rate_limiter.reset()
    yield TestClient(app)
    app.dependency_overrides.clear()
    _rate_limiter.reset()


H = {"X-API-Key": "testkey"}


def _seed_market(db_conn, venue="polymarket", vid="0xM1", title="Will X?",
                 category="politics", status="open"):
    from ingest.core import MarketRecord, ingest
    ingest(db_conn, [MarketRecord(venue_code=venue, venue_market_id=vid,
                                  title=title, raw_rules="rules", category=category,
                                  status=status)])
    with db_conn.cursor() as cur:
        cur.execute("SELECT market_id, snapshot_id FROM rule_snapshots "
                    "JOIN markets USING (market_id) WHERE venue_market_id=%s", (vid,))
        return cur.fetchone()


# ── auth ─────────────────────────────────────────────────────────────────────

def test_health_needs_no_key(client):
    assert client.get("/health").json() == {"ok": True}


def test_missing_key_rejected(client):
    assert client.get("/markets").status_code == 401


def test_invalid_key_rejected(client):
    assert client.get("/markets", headers={"X-API-Key": "nope"}).status_code == 401


def test_valid_key_accepted(client):
    assert client.get("/markets", headers=H).status_code == 200


def test_cors_header_present(client):
    # the file:// dashboard depends on this to fetch cross-origin
    r = client.get("/health", headers={"Origin": "null"})
    assert r.headers.get("access-control-allow-origin") == "*"


def test_rate_limit_enforced(client):
    rl = {"X-API-Key": "rlkey"}            # rate_per_min = 2
    assert client.get("/markets", headers=rl).status_code == 200
    assert client.get("/markets", headers=rl).status_code == 200
    assert client.get("/markets", headers=rl).status_code == 429


# ── endpoints ────────────────────────────────────────────────────────────────

def test_markets_lists_and_filters_by_venue(client, db_conn):
    _seed_market(db_conn, "polymarket", "0xP", "Poly market")
    _seed_market(db_conn, "kalshi", "KX1", "Kalshi market")
    allm = client.get("/markets", headers=H).json()["markets"]
    assert len(allm) == 2
    poly = client.get("/markets?venue=polymarket", headers=H).json()["markets"]
    assert [m["venue_market_id"] for m in poly] == ["0xP"]


def test_market_rules_returns_current_parse(client, db_conn):
    market_id, snapshot_id = _seed_market(db_conn, vid="0xR")
    with db_conn.cursor() as cur:
        cur.execute("INSERT INTO sources (canonical_name) VALUES ('AP') RETURNING source_id")
        sid = cur.fetchone()[0]
        cur.execute("""INSERT INTO parsed_rules (market_id, snapshot_id, source_id,
            resolution_logic, source_fallback, threshold_def, confidence,
            extraction_method, reviewed, is_stale)
            VALUES (%s,%s,%s,'resolves YES if X','media consensus','>=50%%',0.9,'llm',TRUE,FALSE)""",
            (market_id, snapshot_id, sid))
    db_conn.commit()
    r = client.get(f"/markets/{market_id}/rules", headers=H).json()
    assert r["authoritative_source"] == "AP"
    assert r["source_fallback"] == "media consensus"
    assert r["reviewed"] is True


def test_market_rules_404_when_unparsed(client, db_conn):
    market_id, _ = _seed_market(db_conn, vid="0xNoParse")
    assert client.get(f"/markets/{market_id}/rules", headers=H).status_code == 404


def test_equivalences_filter_by_risk_and_type(client, db_conn):
    a = _seed_market(db_conn, "polymarket", "0xA", "A")
    b = _seed_market(db_conn, "kalshi", "KXB", "B")
    with db_conn.cursor() as cur:
        cur.execute("""INSERT INTO equivalences (market_a_id, market_b_id,
            match_type, divergence_axes, risk_score)
            VALUES (%s,%s,'false_friend',ARRAY['source'],0.8)""", (a[0], b[0]))
    db_conn.commit()
    hi = client.get("/equivalences?min_risk=0.5", headers=H).json()["equivalences"]
    assert len(hi) == 1
    assert hi[0]["match_type"] == "false_friend"
    assert hi[0]["market_a_title"] == "A"
    assert client.get("/equivalences?min_risk=0.9", headers=H).json()["equivalences"] == []
    assert client.get("/equivalences?match_type=true_match", headers=H).json()["equivalences"] == []


def test_equivalences_includes_strategy_fields(client, db_conn):
    a = _seed_market(db_conn, "polymarket", "0xSA", "A")
    b = _seed_market(db_conn, "kalshi", "KXSB", "B")
    with db_conn.cursor() as cur:
        cur.execute("""INSERT INTO equivalences (market_a_id, market_b_id, match_type,
            divergence_axes, risk_score, divergence_direction, strategy_scenario,
            strategy_rationale)
            VALUES (%s,%s,'false_friend',ARRAY['threshold'],0.7,'a','A YES on boundary','looser threshold')""",
            (a[0], b[0]))
    db_conn.commit()
    e = client.get("/equivalences", headers=H).json()["equivalences"][0]
    assert e["divergence_direction"] == "a"
    assert e["strategy_scenario"] == "A YES on boundary"
    assert e["strategy_rationale"] == "looser threshold"


def test_market_price_live(client, db_conn, monkeypatch):
    market_id, _ = _seed_market(db_conn, "polymarket", "0xPR", "P")
    import tool.api.main as main
    monkeypatch.setattr(main, "live_price", lambda v, i: {"yes": 0.3, "no": 0.7})
    r = client.get(f"/markets/{market_id}/price", headers=H).json()
    assert r["yes"] == 0.3 and r["no"] == 0.7
    assert r["source"] == "live"
    assert r["venue"] == "polymarket"


def test_market_price_cached_fallback(client, db_conn, monkeypatch):
    # seed a polymarket market whose snapshot payload carries prices
    from ingest.core import MarketRecord, ingest
    ingest(db_conn, [MarketRecord(venue_code="polymarket", venue_market_id="0xCP",
        title="C", raw_rules="r", status="open",
        raw_payload={"outcomes": '["Yes","No"]', "outcomePrices": '["0.4","0.6"]'})])
    with db_conn.cursor() as cur:
        cur.execute("SELECT market_id FROM markets WHERE venue_market_id='0xCP'")
        mid = cur.fetchone()[0]
    db_conn.commit()
    import tool.api.main as main
    monkeypatch.setattr(main, "live_price", lambda v, i: None)   # venue unreachable
    r = client.get(f"/markets/{mid}/price", headers=H).json()
    assert r["yes"] == 0.4
    assert r["source"] == "cached"


def test_market_price_unknown_market_404(client):
    import uuid
    r = client.get(f"/markets/{uuid.uuid4()}/price", headers=H)
    assert r.status_code == 404


def test_rule_changes_feed(client, db_conn):
    market_id, snap1 = _seed_market(db_conn, vid="0xRC")
    with db_conn.cursor() as cur:
        cur.execute("""INSERT INTO rule_snapshots (market_id, raw_rules, content_hash)
                       VALUES (%s,'new rules','h2') RETURNING snapshot_id""", (market_id,))
        snap2 = cur.fetchone()[0]
        cur.execute("""INSERT INTO rule_change_events (market_id, prev_snapshot_id,
                       new_snapshot_id, severity) VALUES (%s,%s,%s,'unknown')""",
                    (market_id, snap1, snap2))
    db_conn.commit()
    feed = client.get("/rule-changes", headers=H).json()["rule_changes"]
    assert len(feed) == 1
    assert feed[0]["new_rules"] == "new rules"
    assert feed[0]["title"] == "Will X?"
