"""
Read-only API over the dataset — THIS is the product surface (the metered data product).

    uvicorn tool.api.main:app --reload

Endpoints (read-only — no writes, no execution):
  GET /markets                 list/filter markets (venue, category, status)
  GET /markets/{id}/rules      current parsed rules + link to raw snapshot
  GET /equivalences            cross-venue pairs; filter by match_type / min risk
  GET /rule-changes            the rule-change alert feed (sellable on its own)

Add API-key auth + per-key rate limiting before exposing — this is the metered product.
Keep responses dataset-shaped (stable JSON schema); the demo tool consumes these.
"""
from __future__ import annotations
import os

try:
    from fastapi import FastAPI, Query, Depends, HTTPException
except ImportError:  # allow import without fastapi installed yet
    FastAPI = None  # type: ignore

if FastAPI is not None:
    app = FastAPI(title="ResMap API", version="0.1.0")

    def db():
        import psycopg
        conn = psycopg.connect(os.environ["DATABASE_URL"])
        try:
            yield conn
        finally:
            conn.close()

    # TODO: replace with real API-key dependency + rate limiting
    def require_key():
        return True

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/markets")
    def list_markets(venue: str | None = None, category: str | None = None,
                     status: str | None = None, _=Depends(require_key)):
        """TODO: query markets with filters; return list of dicts."""
        raise HTTPException(501, "not implemented")

    @app.get("/markets/{market_id}/rules")
    def market_rules(market_id: str, _=Depends(require_key)):
        """TODO: return current (non-stale) parsed_rules + snapshot reference."""
        raise HTTPException(501, "not implemented")

    @app.get("/equivalences")
    def equivalences(match_type: str | None = None, min_risk: float = 0.0,
                     _=Depends(require_key)):
        """TODO: return cross-venue pairs; this is the high-value endpoint."""
        raise HTTPException(501, "not implemented")

    @app.get("/rule-changes")
    def rule_changes(since: str | None = None, _=Depends(require_key)):
        """TODO: return rule_change_events; the alert feed."""
        raise HTTPException(501, "not implemented")
