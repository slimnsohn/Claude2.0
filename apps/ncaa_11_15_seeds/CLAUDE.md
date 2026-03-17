# NCAA 11-15 Seeds

## Overview
NCAA March Madness first round betting tracker — $100 on every 11-15 seed game (20/year). Tracks team names, seeds, odds, and P&L.

## Tech Stack
Static HTML/JS browser app. Data in JSON.

## Quick Start
```bash
start.bat
```

## Project Structure
- `index.html` — Main app (Summary dashboard + filterable Results view)
- `data/results.json` — Historical game data (2008-2025, no 2020)

## Data Format
Each game: `{year, seed, underdog, favorite, odds (American +), won (bool)}`
P&L calculated client-side: win = $100 * odds/100, loss = -$100.

## Skills & Protocols
- **Chat Widget**: `../../_skills/llm-chat-widget/SKILL.md`
- **Security Audit**: `../../_skills/security-audit/SKILL.md`

## Shared Assets
- Base CSS: `<link rel="stylesheet" href="../../_shared/styles/base.css">`
- Fetch wrapper: `<script src="../../_shared/fetch-wrapper.js"></script>`
- Chat widget: `<script src="../../_skills/llm-chat-widget/dist/chat-widget.js"></script>`
