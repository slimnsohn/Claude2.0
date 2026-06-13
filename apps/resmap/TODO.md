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
- [x] Source calibration LAYER 1 (extraction fix, 2026-06-13): parse contract
      now splits the PRIMARY authority (short canonical entity → `sources`)
      from the fallback procedure (new `parsed_rules.source_fallback` column).
      Verified live: FIFA markets collapse 10+ prose rows → one "FIFA";
      NASA → "NASA GISS LOTI". Existing parses re-parsed under the new
      contract; old verbose source rows stay referenced by stale parses
      (history), live equivalence joins only fresh parses so it self-heals.
- [x] Source calibration LAYER 2 ✅ 2026-06-13: `sources.merged_into` self-ref;
      equivalence resolves COALESCE(merged_into, source_id); `review_cli
      list-sources`/`merge-source`; `scripts/cluster_sources` (LLM proposes,
      human approves). Applied live: registry now 12 canonical + 25 aliases;
      Brandon Johnson arrest pair source-axis cleared (0.9→0.45).
- [ ] Review the 51 ≥0.90 pairs (needs ~80 more parses) + tune AXIS_WEIGHTS —
      deferred: tuning is unprincipled without a hand-labelled seed set; build
      the seed set first.

## Hardening (audit 2026-06-13, fixed) ✅
- [x] candidate_matcher date window symmetric (was abs(timedelta.days),
      asymmetric on sub-day gaps); now total_seconds
- [x] ingest commits per 500-record batch — a late-page failure on a long
      ingest keeps completed work, resumes idempotently (was all-or-nothing)
- [x] rule_parser --ids filter is a composable clause, not a brittle
      str.replace on the WHERE text
- [x] `rule_change_events.severity` classifier ✅ 2026-06-13:
      `parse/classify_changes.py` (claude compares prev/new → cosmetic|material
      + diff_summary). Run `python -m parse.classify_changes`.
- [x] API keys hashed ✅ 2026-06-13: `api_keys.key_hash` (sha256); raw key never
      stored; `scripts/make_api_key.py` mints + prints once.

## Phase 4 — product surface ✅ 2026-06-13
- [x] `tool/api/main.py`: read-only endpoints — /markets, /markets/{id}/rules,
      /equivalences, /rule-changes (source resolves through merged_into)
- [x] API-key auth (`api_keys` table, X-API-Key) + per-key sliding-window rate
      limit (`tool/api/auth.py`); CORS for the file:// dashboard; dev key seeded
- [x] `tool/web/dashboard.html`: divergence dashboard — pairs flagged
      true_match/near_match/false_friend, rule-change feed, chat widget.
      `start.bat` launches uvicorn + opens it.
- [x] Auth via hashed keys ✅ (see Hardening above)
- [ ] net-after-fees calc on pairs — DEFERRED BY DESIGN: requires live price
      feeds ResMap deliberately doesn't store ("settlement semantics, not prices").
      Would need a separate price source; out of scope for the dataset product.

## Phase 5 — data product ✅ 2026-06-13
- [x] `export/to_parquet.py`: Postgres → Parquet snapshot (markets/parsed_rules/
      rule_changes partitioned by venue; sources/equivalences flat). parsed_rules
      resolves source through merged_into; all parses exported with is_stale flag
      so buyers keep history. Verified live: 72,641 markets → 6.7 MB, DuckDB-readable.
- [x] Scheduled daily refresh ✅ 2026-06-13: `scripts/daily_refresh.bat`
      (ingest + export only — parse/equiv stay manual/curated) registered as
      Windows Task "ResMap Daily Refresh", 06:00 daily.

## Onboarding website ✅ 2026-06-13
- [x] `tool/web/`: index (landing) + getting-started (step-by-step) + faq
      (concepts) + dashboard (live tool) + control (ops), shared nav. Plain-English
      glossary in the FAQ; non-expert clarity pass across all pages.
- [x] Browser-driven refresh: `tool/api/control.py` (separate localhost control
      server, token-gated) + `tool/web/control.html` "Refresh data now" button —
      runs ingest+export server-side (parse/equiv stay manual). `start.bat` launches
      both servers; `launch.vbs` does it silently (no terminal). Note: a server must
      be started once (a page can't bootstrap itself); after that it's all browser.

## Stretch / later
- [ ] Rule-change alert feed as its own subscription (Telegram/Discord/webhook)
- [ ] Historical price/probability time-series (the "closing line" archive idea)
- [ ] Backtesting harness over the historical dataset
- [ ] Hand-labelled equivalence seed set → calibrate AXIS_WEIGHTS, expand to all 51 ≥0.90 pairs
- [ ] Kalshi signed requests if rate limits bite (key regen at kalshi.com)
- [ ] Gemini in the equivalence layer once Poly↔Kalshi is solid
