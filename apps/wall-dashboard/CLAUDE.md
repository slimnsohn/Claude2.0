# Wall Dashboard

Glanceable wall-mounted TV dashboard (weather + Northbrook trains) plus a phone
widget. Google Apps Script web app, mirrored to this local repo.

## Layout
- `apps-script/` — files pasted into the Apps Script editor (Code.gs, Dashboard.html, appsscript.json)
- `docs/` — Sheet setup + API notes
- `tests/` — Node unit tests for pure logic: `node tests/pure-logic.test.js`

## Rules
- API keys (Metra token) live in the Google Sheet `Config` tab, never in code.
- Pure functions stay GAS-free and are unit-tested; I/O functions are verified with Logger.log.
- Chat-widget exception: the workspace rule to embed the shared chat widget does
  NOT apply here — this is a non-interactive OLED kiosk display. Deliberate, documented.

## Deploy
See `README.md`. Always reuse the existing deployment ID so the Fire Stick URL never breaks.
