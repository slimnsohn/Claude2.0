# Sportsbook Tools — Setup Guide

## What This Is
A mobile-friendly Google Apps Script web app with 4 tools:
- **KALSHI** — Convert Kalshi contract cents to American odds (post taker fee)
- **XBETS** — Cross-book P&L calculator with to-win vs total-return toggle
- **WAGER** — Breakeven hedge calculator (dog/fav cross bet with juice %)
- **CASH** — Quick-entry cashflow logger that writes to your Google Sheet

## Files
- `Code.gs` — Server-side Apps Script (handles sheet reads/writes)
- `Index.html` — Client-side UI (all 4 tabs)

## Setup (5 minutes)

### 1. Open Apps Script Editor
- Go to your spreadsheet
- Click **Extensions → Apps Script**
- If you get a 400 error, go directly to https://script.google.com/home and create a new project

### 2. Add the Server Code
- In the script editor, select `Code.gs`
- Delete everything, paste contents of `Code.gs`

### 3. Add the HTML File
- Click **+** next to "Files" → select **HTML**
- Name it exactly `Index` (capital I, no extension)
- Paste contents of `Index.html`

### 4. Verify Configuration in Code.gs
- Line 2: `SPREADSHEET_ID` — already set to your sheet
- Line 3: `SHEET_NAME` — update to match your actual tab name
- Line 4: `GID` — already set to 1185168702
- Lines 10-11: Column mappings (SS = N/O/P, NK = Q/R/S)
- Line 15: `DATA_START_ROW = 4`

### 5. Deploy
- Click **Deploy → New deployment**
- Gear icon → **Web app**
- Execute as: **Me**
- Who has access: **Anyone** (URL is unguessable, server validates all input)
- Click **Deploy**
- Authorize when prompted (click through "Advanced → Go to project name")
- Copy the web app URL

### 6. Add to Phone
- Open URL in Safari (iOS) or Chrome (Android)
- iOS: Share → "Add to Home Screen"
- Android: 3-dot menu → "Add to Home Screen"

## Updating
After editing Index.html or Code.gs:
1. Save (Ctrl+S)
2. **Deploy → New deployment** (not Manage — Apps Script caches aggressively)
3. Use the new URL

## Security
- Server-side validation: user whitelist, book whitelist, amount bounds, date regex
- No innerHTML with user data (XSS safe)
- No external scripts (only Google Fonts CSS)
- No localStorage/cookies
- Spreadsheet ID only in server-side code
- Google sandbox isolates the HTML iframe

## Book Codes
bo, bk, nv, px, py, fd, ci, cs, ka

## Payout Types
- **To Win** books (show profit): BK, FD, BO
- **Total Return** books (show wager + profit): PY, KA, NV, PX
