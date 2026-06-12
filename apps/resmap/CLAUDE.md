# ResMap — Prediction-Market Resolution Intelligence

> A *dataset* product. The asset is structured knowledge of **how prediction
> markets actually resolve** and **where lookalike markets across venues
> diverge**. The arb/alert tool on top is a demo. API-first, clean storage,
> auditable data.

## North star (do not drift)

Not a price scraper. The asset is the structured answer to: *under exactly what
conditions does this market resolve YES, from what authoritative source, by
what cutoff, and how does it differ from the lookalike on the other venue?*

## Scope for v1

- **Ingestion venues:** Polymarket, Kalshi, Gemini (all live, keyless reads).
- **Equivalence layer:** Polymarket ↔ Kalshi ONLY until it is solid.
- **Read-only.** No custody, execution, or wallets. We sell signal; buyers execute.

## The three data layers (value increases down the list)

1. `markets` — registry, table stakes. 2. `rule_snapshots` → `parsed_rules` —
verbatim immutable rules text, LLM-parsed, human-reviewed. 3. `equivalences` —
cross-venue `true_match` / `near_match` / `false_friend` + risk score.
The `sources` and `equivalences` tables are the proprietary IP.

## Decisions already made (see _docs/ARCHITECTURE.md for rationale)

- Postgres 16 = system of record (native install — see _docs/SETUP_WINDOWS.md).
- Raw rule text append-only + hashed → `rule_change_events` falls out free.
- LLM extraction via `claude -p` CLI (Max plan, no API cost) — parse/claude_cli.py.
- Parse queue is volume-ordered, no cutoff; run in `--limit` batches.
- DuckDB/Parquet = analytical export only, never the source of truth.

## Conventions

- Python 3.13, psycopg v3. Adapters are pure (fetch → yield `MarketRecord`);
  ALL DB writes go through `ingest/core.py`.
- Secrets in `.env`. Tests: pytest; integration tests use `resmap_test` DB.
- Data layer stable, tool layer disposable. Prefer new columns over overwriting.

## What NOT to do

- No order execution / custody / wallets.
- Never auto-accept LLM parses (review via `parse/review_cli.py` is the moat).
- Never throw away raw snapshots or collapse rule history.
- No new equivalence venues until Poly↔Kalshi is solid.

Work `TODO.md` top-down. Architecture detail: `_docs/ARCHITECTURE.md`.
