# TODO

## Phase 1 — Data Ingestion & Schema
- [ ] SQLite schema creation script (db/schema.sql)
- [ ] Database helper class with all CRUD operations
- [ ] Polymarket Gamma API client with pagination
- [ ] Polymarket CLOB orderbook depth fetcher
- [ ] Kalshi API client with cursor pagination + auth
- [ ] Kalshi orderbook depth fetcher
- [ ] Normalizer (common schema for both platforms)
- [ ] Rule snapshot + SHA256 hash change detection
- [ ] Position importer from cashflow logger CSV
- [ ] Test with fixture data

## Phase 2 — Analysis Core
- [ ] Claude API wrapper with retry + rate limiting + spend tracking
- [ ] Prompt templates v1 (system + user, 6 mismatch categories)
- [ ] JSON response parser with validation + fallback handling
- [ ] Severity scorer
- [ ] Liquidity-weighted pre-scan queue (score BEFORE Claude calls)
- [ ] Priority score calculator (severity × liquidity × price × position)
- [ ] Source quirks database (v1 — BLS, AP, Wikipedia, Fed, Box Office Mojo)
- [ ] Inject relevant source quirks into prompt context

## Phase 3 — Cross-Platform Engine
- [ ] Fuzzy title matching with rapidfuzz
- [ ] Date proximity matching
- [ ] Claude-verified cross-platform rule diff
- [ ] Structural arb detector
- [ ] Store matches in cross_platform_matches table

## Phase 4 — Output & Alerts
- [ ] Daily markdown report generator
- [ ] Telegram bot setup
- [ ] Alert function with severity emoji + position overlay
- [ ] Inline actions: Analyze Deeper (rules-adjusted prob)
- [ ] Inline actions: Dismiss (log to dismissed_alerts, stop re-alerting)
- [ ] Inline actions: Track (add to watchlist with price monitoring)
- [ ] Cross-platform arb alert
- [ ] Rule change + position alert
- [ ] Email alert (optional, lower priority)

## Phase 5 — Monitoring
- [ ] Resolution source poller (hash-based change detection)
- [ ] Link source monitors to markets
- [ ] Source update → cross-reference flagged markets → immediate alert
- [ ] Rule change detector (compare snapshots, trigger position alerts)

## Phase 6 — Eval & Calibration
- [ ] Build labeled dataset (25 real mismatches, 25 clean markets)
- [ ] Prompt eval runner (precision, recall, F1)
- [ ] Prompt version tracking in all analysis results
- [ ] Historical resolution backfill pipeline
- [ ] Resolution audit: did market resolve per rules or per title?
- [ ] Calibration metrics: flag accuracy, severity predictiveness, hypothetical PnL
- [ ] Expand labeled dataset to 50+ as live data comes in

## Phase 7 — Scheduling & Polish
- [ ] CLI entry point with all modes
- [ ] Daily cron (full scan)
- [ ] Hourly cron (incremental + source monitoring)
- [ ] Cost tracking (log Claude API spend per run)
- [ ] Auto-pause if daily spend exceeds MAX_DAILY_CLAUDE_SPEND_USD

## Stretch
- [ ] Dashboard (React artifact or simple HTML)
- [ ] Watchlist price monitoring with threshold alerts
- [ ] Auto-import positions via Polymarket/Kalshi API (not just CSV)
- [ ] Multi-model eval (compare Sonnet vs Haiku on mismatch detection)
- [ ] Backtest: if you traded every high-severity flag at market price, what's the PnL?
