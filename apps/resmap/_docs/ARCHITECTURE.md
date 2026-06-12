# Architecture notes

## The one idea
Store **settlement semantics, not prices.** Prices are a commodity feed anyone can buy.
The defensible asset is: *under exactly what conditions does this resolve, from what
authoritative source, by what cutoff, and how does it differ from the lookalike on the
other venue?*

## Why Postgres is the source of truth (not Parquet/DuckDB)
The valuable layers are relationship-heavy and frequently corrected:
- `sources` ↔ many `parsed_rules` (one settlement source feeds many markets)
- `equivalences` is a many-to-many graph between markets, with human edits over time
Parquet/DuckDB are immutable-batch oriented; corrections and many-to-many links are
painful there. So Postgres = system of record; Parquet = periodic analytical export for
backtest/research buyers. One-way: PG → Parquet, never the reverse.

## Append-only raw, derived parsed — and why
`rule_snapshots` is immutable and hashed. Two payoffs:
1. **Auditability** — every structured field in `parsed_rules` references the exact
   snapshot it came from. You can always show "this is the text we read."
2. **Rule-change signal for free** — when a venue edits settlement criteria mid-market,
   the hash changes, a `rule_change_events` row is written, and existing parses are
   flagged stale. "Rules changed mid-market" is high-value risk info and a standalone
   alert product, with zero extra infrastructure.

## The four divergence axes (equivalence engine)
Two markets on the "same" real-world event can still resolve differently. We compare on:
| axis | why it can flip resolution |
|------|----------------------------|
| source | different authoritative source can call the event differently |
| cutoff | a 6pm vs 11:59pm cutoff captures different facts |
| tie | draw/push/void handling differs |
| threshold | ">=50.0%" vs ">50%" and rounding rules differ |

`true_match` (safe) / `near_match` (flag) / `false_friend` (the trap a naive scanner
calls free money). Surfacing `false_friend`s is the product's edge over every cheap
arb tool. Source is weighted highest; calibrate weights on a hand-verified seed set.

## Moat & maintenance
- Moat = the curated `sources` normalization + the `equivalences` graph. Code is cloneable;
  this curation is not.
- Maintenance ≈ keeping two adapters alive + re-reviewing markets whose rules changed.
  Bounded — fits a few hours/week. Rent a unified feed (PolyRouter / Prediction Hunt /
  FinFeedAPI) if adapter upkeep eats too much time; your value-add sits on top regardless.

## Monetization surfaces (all ride the same dataset)
1. Metered read API over markets / parsed rules / equivalences (B2B, tool-builders).
2. Rule-change + false-friend alert feed (subscription).
3. Parquet historical export (backtesters/researchers).
The arb/alert web tool is a demo to sell #1–#3, not the product itself.

## Explicitly out of scope for v1
Execution, custody, wallets, live latency competition with bots.
We sell signal/data; the buyer executes.

## Build decisions (locked 2026-06-12)

- **Native PostgreSQL 16** (winget), not Docker — the DB must be up for
  scheduled ingest without Docker Desktop running. See SETUP_WINDOWS.md.
- **LLM via `claude -p` CLI** (parse/claude_cli.py), not the Anthropic API —
  zero per-call cost on the Max plan. Throughput is the tradeoff: minutes per
  ~10 markets, hence the volume-ordered parse queue + `--limit` batches.
- **Gemini added as a third ingestion venue** (user decision). Its contracts
  carry real settlement text in a rich-text `description` tree, public API,
  no auth. Scope guard: Gemini is *ingestion-only* — the equivalence layer
  stays Poly↔Kalshi until solid, per the original hard rule.
- **Kalshi market data is public** — RSA-PSS signing (kept, proven) is only
  needed for private endpoints; the adapter signs when creds exist and runs
  unsigned otherwise. No credential blocker for ingestion.
- **Parse queue policy: volume-ordered, no cutoff.** Every market eventually
  parses; high-volume first. Empty-rules markets (Kalshi multi-leg parlays)
  are registry-only and skipped by the parser.
