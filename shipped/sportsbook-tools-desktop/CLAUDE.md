# Sportsbook Tools Desktop

## Overview
Electron desktop app. 3 tabs: Kalshi odds converter, cross-book P&L calculator (Xbets), wager hedge calculator. Desktop counterpart to the iOS PWA version.

## Tech Stack
Electron 28, vanilla HTML/JS. No build step.

## Quick Start
```bash
start.bat
```
Or double-click `launch.vbs` for no terminal.

## Project Structure
- `main.js` — Electron main process (window config)
- `index.html` — All UI + logic (single file)
- `package.json` — Electron dependency only

## Differences from iOS Version
- No Cashflow tab (that needs Google Sheets/Apps Script)
- Has full conversion table dropdown on Kalshi tab
- Desktop drag bar + keyboard nav (1/2/3 for tabs)
- Hover states on buttons
