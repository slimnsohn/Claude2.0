# TODO

Work top to bottom. Each phase is independently testable. Check off as you go.

## Phase 0 — environment ✅ 2026-06-12
- [x] PostgreSQL 16 native via winget; service `postgresql-x64-16` running
- [x] Role `resmap` + DBs `resmap` / `resmap_test`; schema loaded into both
- [x] `.env` from `.env.example` (DB URLs, CLAUDE_CLI_MODEL, PGSUPERPASSWORD)
- [x] venv + `pip install -r requirements.txt`
- [x] `pytest tests/` — change-detection unit tests pass

## Phase 1 — ingestion (Layer 1: registry) ✅ 2026-06-12
- [x] `ingest/adapters/polymarket.py` — Gamma API, conditionId, HTML-stripped rules
- [x] `ingest/adapters/kalshi.py` — public /markets, optional RSA-PSS signing
- [x] `ingest/adapters/gemini.py` — events→contracts, rich-text rules flattening
- [x] `ingest/run.py` — --venue / --max-pages, per-venue transaction batches
- [x] Live gate: run once → markets + rule_snapshots populate (3,012 markets)
- [x] Live gate: run again → `unchanged` == count, ZERO new snapshots (all venues)
- [x] Simulated rule edit → `rule_change_events` row + `parsed_rules.is_stale`
      flip (tests/test_ingest_db.py + scripts/verify_phase1.py)

## Phase 2 — rule parsing (Layer 2: semantics) ✅ 2026-06-12
- [x] `parse/claude_cli.py` — `claude -p` wrapper (retries, JSON extraction)
- [x] `parse/rule_parser.py` — 9-key contract, volume-ordered queue, per-row
      commits, `reviewed=false`, `extraction_method='llm'`
- [x] Settlement sources normalized into `sources` (dedupe by canonical_name)
- [x] `parse/review_cli.py` — list / show / approve (no auto-accept path)
- [x] Re-parse loop: `is_stale=true` markets re-selected automatically
- [ ] Ongoing: parse the backlog in `--limit` batches; review queue weekly

## Phase 3 — equivalence (Layer 3: the moat)
- [ ] `parse/candidate_matcher.py`: surface likely same-event pairs across
      Poly↔Kalshi (title similarity + category + date window). Cheap recall,
      human confirms.
- [ ] `parse/equivalence.py`: compare two parsed interpretations across the 4
      axes (source, cutoff, tie, threshold) → `match_type`, `divergence_axes`,
      `risk_score`
- [ ] Seed with a handful of hand-verified pairs to calibrate risk scoring

## Phase 4 — product surface
- [ ] `tool/api/`: read-only endpoints — markets, parsed rules, equivalences,
      rule-change feed
- [ ] API auth + per-key rate limiting (this is the metered data product)
- [ ] `tool/web/`: thin live arb/alert dashboard consuming the API (the DEMO)
      — show net-after-fees, and CRUCIALLY filter out `false_friend` pairs

## Phase 5 — data product
- [ ] `export/to_parquet.py`: Postgres → partitioned Parquet for DuckDB consumers
- [ ] Decide cadence (daily snapshot of resolved markets + rule history)

## Stretch / later
- [ ] Schedule `ingest.run` (Task Scheduler, daily)
- [ ] Rule-change alert feed as its own subscription (Telegram/Discord/webhook)
- [ ] Historical price/probability time-series (the "closing line" archive idea)
- [ ] Backtesting harness over the historical dataset
- [ ] Kalshi signed requests if rate limits bite (key regen at kalshi.com)
- [ ] Gemini in the equivalence layer once Poly↔Kalshi is solid
