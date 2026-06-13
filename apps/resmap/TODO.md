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

## Phase 3 — equivalence (Layer 3: the moat) ✅ 2026-06-12
- [x] `parse/candidate_matcher.py` — rapidfuzz titles + date window, rules-text
      required (parlays excluded); 35,798 raw candidates, 51 at ≥0.90
- [x] `parse/equivalence.py` — 4-axis compare: deterministic fast paths + LLM
      judge for ambiguous axes; risk-weighted → match_type; upserts
- [x] `scripts/equivalence_pipeline.py` — staged match → parse → compare
- [x] Live seed: top 12 pairs compared; hand-verified the headline find —
      "hottest year on record" is a TRUE false_friend (Poly resolves rank/tie
      = YES, Kalshi strict inequality = NO on the same tie)
- [ ] Calibration: curate `sources` rows so the source axis fires on real
      authority differences, not canonical-name granularity (currently
      inflates risk on pairs sharing a primary source with different
      fallback chains). NOTE: canonical_name is UNIQUE, so dedup is semantic —
      a human curation step or a judge call on near-name sources, not a code
      fix. Decide the approach before tuning weights.
- [ ] Review the 51 ≥0.90 pairs; extend seed set; tune AXIS_WEIGHTS

## Hardening (audit 2026-06-13, fixed) ✅
- [x] candidate_matcher date window symmetric (was abs(timedelta.days),
      asymmetric on sub-day gaps); now total_seconds
- [x] ingest commits per 500-record batch — a late-page failure on a long
      ingest keeps completed work, resumes idempotently (was all-or-nothing)
- [x] rule_parser --ids filter is a composable clause, not a brittle
      str.replace on the WHERE text
- [ ] `rule_change_events.severity` is always 'unknown' — wire re-parse to
      classify cosmetic/material (Phase 2.5; the schema already has the column)

## Phase 4 — product surface (NEXT)
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
