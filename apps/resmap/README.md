# ResMap

Prediction-market **resolution intelligence** — a dataset product. The asset is
structured knowledge of *how* Polymarket, Kalshi & Gemini markets resolve, and
*where lookalike markets across venues diverge*. A thin arb/alert tool sits on
top as the demo.

**Read `CLAUDE.md` first** — north star + decisions. Then work `TODO.md` top-down.

## Why this is defensible
A naive arb scanner does price arithmetic anyone can copy. The value here is the
resolution-rule database and the cross-venue divergence graph — expensive to
compile, compounding over time, human-curated. The `sources` and `equivalences`
tables are the IP.

## Quickstart (Windows, native Postgres — see _docs/SETUP_WINDOWS.md)
```powershell
# one-time: PostgreSQL 16 via winget + role/DBs + schema (full steps in _docs/SETUP_WINDOWS.md)
copy .env.example .env             # fill in values
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m pytest tests\ -q       # 105 tests, all green

.\.venv\Scripts\python -m ingest.run                          # pull all 3 venues
.\.venv\Scripts\python -m parse.rule_parser --limit 20        # LLM-extract rules (claude -p)
.\.venv\Scripts\python -m parse.review_cli list               # human review queue
.\.venv\Scripts\python -m parse.equivalence                   # cross-venue divergence scoring
```
(docker-compose.yml remains as an alternative DB path for other machines.)

## Layout
```
db/schema.sql            Postgres system of record (3 data layers)
ingest/core.py           change-detection engine (hash-based, validated)
ingest/adapters/         polymarket.py, kalshi.py, gemini.py → yield MarketRecord
ingest/run.py            ingest loop (--venue, --max-pages)
parse/claude_cli.py      `claude -p` subprocess wrapper (no API cost)
parse/rule_parser.py     raw rules → structured parsed_rules (human-reviewed)
parse/review_cli.py      list / show / approve — the human-in-the-loop moat
parse/candidate_matcher.py  surface same-event pairs across venues   (Phase 3)
parse/equivalence.py     four-axis divergence scoring ← the moat     (Phase 3)
tool/api/                read-only metered API (the product surface) (Phase 4)
export/to_parquet.py     Postgres → Parquet for analytical buyers    (Phase 5)
scripts/verify_phase1.py end-to-end change-detection demo
_docs/                   ARCHITECTURE.md, SETUP_WINDOWS.md
```

## Hard rules
- Read-only. No custody/execution/wallets.
- Raw rule text is append-only; never overwrite history.
- Don't auto-accept LLM parses — the human review is the moat.
- Equivalence layer stays Poly ↔ Kalshi until solid (Gemini is ingestion-only).
