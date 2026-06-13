"""
Read-only API over the dataset — THIS is the product surface (the metered data
product). All endpoints are read-only: no writes, no execution.

    uvicorn tool.api.main:app --reload     # needs DATABASE_URL

Auth: every endpoint except /health requires an `X-API-Key` header matching an
active row in `api_keys`; requests are rate-limited per key (sliding window).

  GET /health                 liveness (no key)
  GET /markets                list/filter markets (venue, category, status, limit)
  GET /markets/{id}/rules     current (non-stale) parsed rules + raw snapshot ref
  GET /equivalences           cross-venue pairs; filter by match_type / min_risk
  GET /rule-changes           the rule-change alert feed (sellable on its own)

Responses are dataset-shaped stable JSON; the demo dashboard consumes these.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from tool.api.auth import RateLimiter, lookup_key
from tool.api.pricing import extract_price, live_price

load_dotenv()  # so `uvicorn tool.api.main:app` picks up DATABASE_URL from .env

app = FastAPI(title="ResMap API", version="1.0.0",
              description="Prediction-market resolution-intelligence — read-only.")

# The demo dashboard is opened as a file:// page (origin "null") and fetches
# this API cross-origin. Data is read-only and gated by X-API-Key, so a
# permissive CORS policy is acceptable for the demo surface.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"],
                   allow_headers=["*"])

_rate_limiter = RateLimiter()


def get_db():
    import psycopg
    conn = psycopg.connect(os.environ["DATABASE_URL"])
    try:
        yield conn
    finally:
        conn.close()


def require_key(x_api_key: str = Header(default=""), conn=Depends(get_db)) -> dict:
    """Validate the API key and enforce its per-minute rate limit."""
    key = lookup_key(conn, x_api_key)
    if not key:
        raise HTTPException(401, "missing or invalid API key (X-API-Key header)")
    if not _rate_limiter.allow(key["key_hash"], key["rate_per_min"]):
        raise HTTPException(429, f"rate limit exceeded ({key['rate_per_min']}/min)")
    return key


def _rows_to_dicts(cur) -> list[dict]:
    cols = [c.name for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/markets")
def list_markets(venue: str | None = None, category: str | None = None,
                 status: str | None = None, limit: int = Query(100, le=1000),
                 conn=Depends(get_db), _=Depends(require_key)):
    clauses, params = [], []
    if venue:
        clauses.append("v.code = %s"); params.append(venue)
    if category:
        clauses.append("m.category = %s"); params.append(category)
    if status:
        clauses.append("m.status = %s"); params.append(status)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT m.market_id, v.code AS venue, m.venue_market_id, m.title,
                   m.category, m.status, m.closes_at, m.resolved_at, m.outcome
            FROM markets m JOIN venues v USING (venue_id)
            {where}
            ORDER BY m.last_seen_at DESC
            LIMIT %s
        """, (*params, limit))
        return {"markets": _rows_to_dicts(cur)}


@app.get("/markets/{market_id}/rules")
def market_rules(market_id: str, conn=Depends(get_db), _=Depends(require_key)):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT p.parsed_id, s.canonical_name AS authoritative_source,
                   p.source_fallback, p.resolution_logic, p.cutoff_time,
                   p.cutoff_basis, p.tie_handling, p.revision_handling,
                   p.threshold_def, p.confidence, p.reviewed,
                   p.snapshot_id, snap.fetched_at AS snapshot_fetched_at
            FROM parsed_rules p
            JOIN rule_snapshots snap USING (snapshot_id)
            LEFT JOIN sources s ON s.source_id = COALESCE(
                (SELECT merged_into FROM sources WHERE source_id = p.source_id),
                p.source_id)
            WHERE p.market_id = %s::uuid AND p.is_stale = FALSE
            ORDER BY p.created_at DESC
            LIMIT 1
        """, (market_id,))
        rows = _rows_to_dicts(cur)
    if not rows:
        raise HTTPException(404, "no current parsed rules for this market")
    return rows[0]


@app.get("/markets/{market_id}/price")
def market_price(market_id: str, conn=Depends(get_db), _=Depends(require_key)):
    """Current YES/NO price: live from the venue, falling back to the
    last-ingested snapshot. Polymarket + Kalshi only."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT v.code, m.venue_market_id, s.raw_payload, s.fetched_at
            FROM markets m
            JOIN venues v USING (venue_id)
            LEFT JOIN LATERAL (
                SELECT raw_payload, fetched_at FROM rule_snapshots
                WHERE market_id = m.market_id ORDER BY fetched_at DESC LIMIT 1
            ) s ON TRUE
            WHERE m.market_id = %s::uuid
        """, (market_id,))
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, "unknown market")
    venue, venue_market_id, payload, fetched_at = row

    live = live_price(venue, venue_market_id)
    if live:
        return {**live, "source": "live", "venue": venue,
                "as_of": datetime.now(timezone.utc)}
    cached = extract_price(venue, payload or {})
    if cached:
        return {**cached, "source": "cached", "venue": venue, "as_of": fetched_at}
    raise HTTPException(404, f"no price available for {venue} market")


@app.get("/equivalences")
def equivalences(match_type: str | None = None, min_risk: float = 0.0,
                 limit: int = Query(100, le=1000),
                 conn=Depends(get_db), _=Depends(require_key)):
    clauses = ["e.risk_score >= %s"]
    params: list = [min_risk]
    if match_type:
        clauses.append("e.match_type = %s"); params.append(match_type)
    where = "WHERE " + " AND ".join(clauses)
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT e.equivalence_id, e.match_type, e.risk_score,
                   e.divergence_axes, e.divergence_notes,
                   e.divergence_direction, e.strategy_scenario, e.strategy_rationale,
                   ma.title AS market_a_title, va.code AS market_a_venue,
                   mb.title AS market_b_title, vb.code AS market_b_venue,
                   e.market_a_id, e.market_b_id, e.updated_at
            FROM equivalences e
            JOIN markets ma ON ma.market_id = e.market_a_id
            JOIN venues va ON va.venue_id = ma.venue_id
            JOIN markets mb ON mb.market_id = e.market_b_id
            JOIN venues vb ON vb.venue_id = mb.venue_id
            {where}
            ORDER BY e.risk_score DESC
            LIMIT %s
        """, (*params, limit))
        return {"equivalences": _rows_to_dicts(cur)}


@app.get("/rule-changes")
def rule_changes(since: str | None = None, limit: int = Query(100, le=1000),
                 conn=Depends(get_db), _=Depends(require_key)):
    clauses, params = [], []
    if since:
        clauses.append("e.detected_at >= %s"); params.append(since)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT e.event_id, e.market_id, m.title, v.code AS venue,
                   e.detected_at, e.severity,
                   prev.raw_rules AS prev_rules, new.raw_rules AS new_rules
            FROM rule_change_events e
            JOIN markets m USING (market_id)
            JOIN venues v USING (venue_id)
            LEFT JOIN rule_snapshots prev ON prev.snapshot_id = e.prev_snapshot_id
            JOIN rule_snapshots new ON new.snapshot_id = e.new_snapshot_id
            {where}
            ORDER BY e.detected_at DESC
            LIMIT %s
        """, (*params, limit))
        return {"rule_changes": _rows_to_dicts(cur)}
