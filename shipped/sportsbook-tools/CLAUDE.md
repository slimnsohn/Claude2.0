# Sportsbook Tools

## Overview
iOS PWA deployed via Google Apps Script. 4 tabs: Kalshi odds converter, cross-book P&L calculator, wager hedge calculator, cashflow logger to Google Sheets.

## Tech Stack
Google Apps Script (Code.gs server + Index.html client). No local runtime — deployed as a GAS web app, added to iOS home screen.

## Project Type
IOS_APP — no start.bat, no local server. Deploy via Apps Script editor.

## Files
- `Code.gs` — Server-side: sheet reads/writes, validation
- `Index.html` — Client-side: all 4 tab UIs + logic
- `SETUP.md` — Deployment guide

## Deploy
1. Paste Code.gs + Index.html into Apps Script editor
2. Deploy > New deployment > Web app
3. Open URL in Safari > Add to Home Screen

## Conventions
- Server-side validation for all sheet writes (user, book, amount, date)
- Book codes: bo, bk, nv, px, py, fd, ci, cs, ka
- Users: SS, NK
- Spreadsheet ID + GID configured in Code.gs lines 2-4
