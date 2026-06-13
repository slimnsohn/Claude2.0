# Resolution Rule Mismatch Detector

## What This Does
Pulls active markets from Polymarket + Kalshi, compares title vs resolution
rules using Claude Code CLI (`claude -p`), flags mismatches that retail traders would miss.
Cross-references across platforms for structural arb. Monitors resolution
sources. Overlays your positions for urgency scoring.

## Stack
- Python 3.11+
- SQLite (local DB — schema in db/schema.sql)
- Claude Code CLI (`claude -p` — Max plan, no per-call API cost)
- python-telegram-bot (alerts with inline actions)
- rapidfuzz (cross-platform matching)

## Key Commands
- `python main.py --mode=daily` — full scan (liquidity-prioritized)
- `python main.py --mode=incremental` — check for rule changes + new markets only
- `python main.py --mode=cross-platform` — run cross-platform matching + arb detection
- `python main.py --mode=monitor` — poll resolution sources for updates
- `python main.py --mode=report` — regenerate report from latest data
- `python main.py --mode=eval --prompt-version=v2` — run prompt A/B eval
- `python main.py --mode=audit` — backfill + calibration metrics
- `python main.py --mode=import-positions --file=positions.csv` — import positions

## Architecture Principles
- Data layers stable, app layers disposable
- SQLite schema is the source of truth — never lose data
- All prompts versioned in prompts.py — track which version produced which results
- Scoring happens BEFORE Claude CLI calls — don't waste calls on illiquid markets
- Every analysis stores prompt_version for traceability

## Config (.env)
- KALSHI_API_KEY (no Anthropic key needed — uses Claude Code CLI)
- TELEGRAM_BOT_TOKEN
- TELEGRAM_CHAT_ID

## Thresholds (config.py)
- MIN_VOLUME_THRESHOLD = 10000
- HIGH_SEVERITY_PRICE_THRESHOLD = 0.70
- ANALYSIS_BATCH_SIZE = 50
- CROSS_PLATFORM_MATCH_THRESHOLD = 0.65
- MAX_DAILY_CLAUDE_CALLS = 500
- SOURCE_POLL_INTERVAL_HOURS = 6

## Testing
- `pytest tests/` — unit tests
- `python main.py --mode=eval` — prompt quality eval against labeled dataset
- Target: precision > 0.80, recall > 0.70 on labeled set before going live
