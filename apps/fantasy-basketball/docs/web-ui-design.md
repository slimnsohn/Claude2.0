# Web UI — Design Spec (2026-06-16)

A read-only web UI to explore the fantasy-basketball data lake, plus an
interactive draft cockpit. Replaces the old project's Flask UI; far richer data.

## Design principle
**Google-clean, not Yahoo-cluttered.** Intuitive and simple. Generous
whitespace, minimal chrome, one accent color, fast. Every screen answers one
question well. No feature unless it earns its place.

## Architecture
- **Flask** app (`app.py`) in `apps/fantasy-basketball/`, **read-only** over
  `data/fbball.duckdb`. Endpoints are thin: they call the already-tested
  `fbball` modules (`valuation`, `draft`, `recommend`, `projections`,
  `yahoo_history`, `db`) and return JSON.
- **Single tabbed page** (`web/index.html` + `web/app.js` + `web/app.css`).
  Chat widget + styling load once.
- Flask mounts static routes `/shared/*` and `/widget/*` serving the workspace
  `_shared/` and `_skills/llm-chat-widget/dist/` dirs — no asset duplication.
  Uses `base.css` theme variables; includes the Gemini chat widget.
- `start.bat`: venv + install Flask + run `app.py` + open browser.

## Tabs & API
1. **Overview** — `/api/overview`: lake summary (seasons, row/player/team
   counts), your team (`slimpickens`) snapshot, league quick facts.
2. **Players** — `/api/players?search=&season=` (table), `/api/player/<id>/seasons`
   (accordion: full per-season history on row click).
3. **Rankings** — `/api/rankings?source=&punt=&pos=&min_gp=`: 9-cat z-scores;
   source = season | recent | projection.
4. **Draft cockpit** — `/api/draft/board?source=&punt=&pos=` (configurable,
   tiered) + live mode (client-side draft state). `/api/draft/recommend` takes
   drafted ids + my ids → needs-weighted best-available.
5. **League** — `/api/league/rosters`, `/api/league/standings`,
   `/api/league/history` (champions, owners by canonical identity, draft years).

## Data flow
Browser `fetch` → Flask API → `fbball` modules / DuckDB (read-only) → JSON.
Draft live-state is browser-session only (refresh resets). No writes to the lake.

## Testing
- Flask test client over a small seeded temp DuckDB; thin API assertions
  (heavy logic already covered by 115 existing tests).
- Boot smoke-test: server starts, key endpoints return expected JSON.

## Out of scope (v1)
Auth, Yahoo writes, data editing, server-side draft persistence.
