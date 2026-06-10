# polymarket-trader

## Overview
Autonomous multi-strategy trading system for Polymarket: arb scanner, market maker, crypto fair-value model, calibration harvester, with a self-learning capital allocator. Paper mode by default; live requires env vars + `live_armed: true` in config.

## Tech Stack
Python 3.11 asyncio · py-clob-client · FastAPI dashboard · SQLite (WAL) · pytest

## Quick Start
```bash
start.bat          # starts watchdog + trader (paper mode) + opens dashboard
.venv\Scripts\python -m pytest    # run tests
.venv\Scripts\python scripts\recon.py          # re-verify API assumptions
.venv\Scripts\python scripts\fetch_history.py  # pull historical data
```

## Env Vars (live mode only — never hardcode, never log)
- `POLYMARKET_PRIVATE_KEY` — wallet key (export from Polymarket settings)
- `POLYMARKET_FUNDER_ADDRESS` — proxy/funder wallet address
- `POLYMARKET_SIGNATURE_TYPE` — 0 browser wallet, 1 email/Magic, 2 safe

## Mode progression
backtest → paper (default) → live. Live flip: pass statistical gates (dashboard shows status), run security-audit skill, set `mode: live` + `live_armed: true` in `config/settings.yaml`.

## Key docs
- Spec: `../../docs/superpowers/specs/2026-06-09-polymarket-trader-design.md`
- Plan: `../../docs/superpowers/plans/2026-06-09-polymarket-trader.md`
