-- ResMap: Prediction-Market Resolution Intelligence
-- System of record (Postgres). Analytical exports go to Parquet/DuckDB separately.
--
-- Design principles:
--  1. Raw rule text is IMMUTABLE and append-only. We never overwrite it, because
--     "the rules changed mid-market" is itself a high-value signal.
--  2. Parsed interpretation is DERIVED and points back to the exact raw snapshot
--     it came from, so every structured field is auditable to source text.
--  3. The `sources` and `equivalences` tables are the proprietary IP. Guard them.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";  -- for gen_random_uuid()

-- ─────────────────────────────────────────────────────────────────────────────
-- Layer 0: venues
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE venues (
    venue_id    SMALLINT PRIMARY KEY,
    code        TEXT NOT NULL UNIQUE,        -- 'polymarket', 'kalshi', 'gemini'
    display_name TEXT NOT NULL
);

INSERT INTO venues (venue_id, code, display_name) VALUES
    (1, 'polymarket', 'Polymarket'),
    (2, 'kalshi',     'Kalshi'),
    (3, 'gemini',     'Gemini');   -- ingestion only; equivalence stays Poly<->Kalshi for v1

-- ─────────────────────────────────────────────────────────────────────────────
-- Layer 1: market registry (the spine)
-- One row per market per venue. Identifiers differ wildly between venues, so we
-- keep both the venue-native id and our own stable internal id.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE markets (
    market_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    venue_id         SMALLINT NOT NULL REFERENCES venues(venue_id),
    venue_market_id  TEXT NOT NULL,          -- e.g. Kalshi ticker, Polymarket condition_id
    title            TEXT NOT NULL,
    category         TEXT,                   -- politics, econ, crypto, sports, ...
    opened_at        TIMESTAMPTZ,
    closes_at        TIMESTAMPTZ,            -- trading close (venue-stated)
    resolved_at      TIMESTAMPTZ,           -- when settlement actually occurred
    outcome          TEXT,                   -- 'YES' / 'NO' / 'INVALID' / NULL if open
    status           TEXT NOT NULL DEFAULT 'open',  -- open | closed | resolved | voided
    first_seen_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (venue_id, venue_market_id)
);
CREATE INDEX idx_markets_status   ON markets(status);
CREATE INDEX idx_markets_category ON markets(category);
CREATE INDEX idx_markets_closes   ON markets(closes_at);

-- ─────────────────────────────────────────────────────────────────────────────
-- Layer 2a: RAW rule snapshots (append-only, immutable)
-- Every fetch of a market's settlement criteria is stored verbatim. We hash the
-- text so we can cheaply detect when a venue EDITS the rules.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE rule_snapshots (
    snapshot_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    market_id     UUID NOT NULL REFERENCES markets(market_id),
    fetched_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw_rules     TEXT NOT NULL,             -- verbatim settlement criteria text
    content_hash  TEXT NOT NULL,             -- sha256 of normalized raw_rules
    raw_payload   JSONB                      -- full API blob for forensic re-parse
);
CREATE INDEX idx_snap_market ON rule_snapshots(market_id, fetched_at DESC);
CREATE INDEX idx_snap_hash   ON rule_snapshots(market_id, content_hash);

-- ─────────────────────────────────────────────────────────────────────────────
-- Layer 0b: authoritative settlement sources (normalized, proprietary)
-- Lets you query "every market that resolves off the AP race call" — a question
-- no competitor can answer without having done this normalization work.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE sources (
    source_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_name TEXT NOT NULL UNIQUE,     -- 'AP race call', 'BLS CPI release', ...
    source_type  TEXT,                       -- official_data | media_call | exchange_discretion | onchain | other
    merged_into  UUID REFERENCES sources(source_id),  -- NULL = canonical; set = alias of another row (curator-merged)
    notes        TEXT
);
CREATE INDEX idx_sources_merged ON sources(merged_into) WHERE merged_into IS NOT NULL;

-- ─────────────────────────────────────────────────────────────────────────────
-- Layer 2b: PARSED rules (derived, mutable, auditable to a snapshot)
-- LLM-assisted extraction → structured fields, human-reviewed. Always references
-- the exact snapshot it was derived from.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE parsed_rules (
    parsed_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    market_id        UUID NOT NULL REFERENCES markets(market_id),
    snapshot_id      UUID NOT NULL REFERENCES rule_snapshots(snapshot_id),
    source_id        UUID REFERENCES sources(source_id),  -- PRIMARY authority (short canonical entity)
    source_fallback  TEXT,         -- secondary/fallback procedure if primary is unavailable
    resolution_logic TEXT,         -- plain-language normalized "resolves YES if ..."
    cutoff_time      TIMESTAMPTZ,  -- the actual settlement cutoff (may differ from closes_at)
    cutoff_basis     TEXT,         -- how cutoff is defined: 'event_time' | 'data_release' | 'venue_stated'
    tie_handling     TEXT,         -- what happens on a tie/draw/push
    revision_handling TEXT,        -- what happens if the data source is later revised
    threshold_def    TEXT,         -- exact threshold/rounding (e.g. ">= 50.0%" vs "> 50%")
    extraction_method TEXT NOT NULL DEFAULT 'llm',  -- llm | manual | llm_reviewed
    confidence       REAL,         -- model/curator confidence 0..1
    reviewed         BOOLEAN NOT NULL DEFAULT FALSE,
    is_stale         BOOLEAN NOT NULL DEFAULT FALSE, -- set TRUE when a newer snapshot appears
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_parsed_market ON parsed_rules(market_id) WHERE is_stale = FALSE;
CREATE INDEX idx_parsed_source ON parsed_rules(source_id);
CREATE INDEX idx_parsed_review ON parsed_rules(reviewed, is_stale);

-- ─────────────────────────────────────────────────────────────────────────────
-- Layer 3: cross-venue equivalence + divergence (the crown jewel)
-- For markets that LOOK like the same event, store whether they actually resolve
-- identically. This is the resolution-mismatch detector's output, persisted.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE equivalences (
    equivalence_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    market_a_id      UUID NOT NULL REFERENCES markets(market_id),
    market_b_id      UUID NOT NULL REFERENCES markets(market_id),
    parsed_a_id      UUID REFERENCES parsed_rules(parsed_id),  -- the interpretations compared
    parsed_b_id      UUID REFERENCES parsed_rules(parsed_id),
    match_type       TEXT NOT NULL,    -- 'true_match' | 'near_match' | 'false_friend'
    divergence_axes  TEXT[],           -- which dims differ: {'source','cutoff','tie','threshold'}
    divergence_notes TEXT,             -- human explanation of the risk
    risk_score       REAL,             -- 0 = safe to treat as same, 1 = will resolve differently
    detected_by      TEXT NOT NULL DEFAULT 'auto',  -- auto | reviewed
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (market_a_id <> market_b_id),
    UNIQUE (market_a_id, market_b_id)
);
CREATE INDEX idx_equiv_type ON equivalences(match_type);
CREATE INDEX idx_equiv_risk ON equivalences(risk_score DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- Derived signal: rule-change events (free byproduct of append-only snapshots)
-- Populated whenever change-detection finds a new hash for an existing market.
-- This table is itself a sellable alert feed.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE rule_change_events (
    event_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    market_id       UUID NOT NULL REFERENCES markets(market_id),
    prev_snapshot_id UUID REFERENCES rule_snapshots(snapshot_id),
    new_snapshot_id  UUID NOT NULL REFERENCES rule_snapshots(snapshot_id),
    detected_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    severity        TEXT,   -- cosmetic | material | unknown (set on re-parse)
    diff_summary    TEXT
);
CREATE INDEX idx_rce_market ON rule_change_events(market_id, detected_at DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- API access: keys for the metered read-only product surface (tool/api).
-- Rate limiting is enforced per key (sliding window, in-process — see auth.py).
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE api_keys (
    api_key      TEXT PRIMARY KEY,
    label        TEXT NOT NULL,                 -- who/what the key is for
    rate_per_min INT  NOT NULL DEFAULT 60,
    active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
