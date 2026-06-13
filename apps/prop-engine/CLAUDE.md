# Prop Engine

## Overview
Market-anchored player-prop EV engine. v1: WNBA. Pulls lines from The Odds API, de-vigs via Shin's method, blends sharp-book consensus, applies rest/teammate-out residual adjustments, surfaces +EV plays with fractional Kelly stakes on a local Flask dashboard.

## Tech Stack
Python 3.11+, Flask, SQLite, scipy, requests.

## Quick Start
```
start.bat
```

## Project Structure
- `core/` — sport-agnostic math, storage, dashboard
- `sports/wnba/` — Odds API + stats.wnba.com adapters, features, residuals
- `cli.py` — pipeline orchestration entrypoint
- `server.py` — Flask dev server
- `scripts/setup_scheduler.ps1` — Windows Task Scheduler registration

## Skills & Protocols
- Security Audit: `../../_skills/security-audit/SKILL.md`
- Chat Widget: `../../_skills/llm-chat-widget/SKILL.md`

## Shared Assets
- Base CSS: `<link rel="stylesheet" href="/_shared/styles/base.css">`
- Fetch wrapper: `<script src="/_shared/fetch-wrapper.js"></script>`
- Chat widget: `<script src="/_skills/llm-chat-widget/dist/chat-widget.js"></script>`

## Environment Variables
- `ODDS_API_KEY` — required for live runs (sign up at the-odds-api.com)
- `GEMINI_API_KEY` — required for chat widget
