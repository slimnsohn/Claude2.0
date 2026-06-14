# Fantasy Basketball Decision Engine

## Overview
Decision engine for a Yahoo H2H 9-cat fantasy basketball league (FG%, FT%, 3PM, PTS, REB, AST, STL, BLK, TO). Historical NBA data lake → valuation engine → decision surfaces (draft, waivers, start/sit, trades).

**Build philosophy:** Data layers stable first, app layers disposable. Lock ingestion + storage before touching the model. Full spec lives in `docs/BUILD-SPEC.md`.

## Tech Stack
Python · `nba_api` (NBA stats) · `yahoo_fantasy_api` (league) · DuckDB / Parquet (storage). No web surface yet — decision surfaces come last and are disposable.

## Build Order (dependency-correct)
1. **Data aggregation** ⭐ CURRENT — `ingest.py` + DuckDB, backfill 3–4 seasons, resumable, rate-limited.
2. **Yahoo auth + league pull** — OAuth2, cache refresh token, verify vs the app.
3. **Valuation engine** — z-scores → punt-aware → volume-weighted %-cats.
4. **Decision surfaces** — waivers/start-sit, then trades, then draft board.

## Two decoupled data sources
- **NBA stats** (`nba_api`) — public, rate-limited. League-wide performance universe.
- **Yahoo league** (Yahoo API) — OAuth2, auth-gated. Your rosters/matchups.
- They join ONLY at `player_id`. Never conflate. Yahoo OAuth must not block stats ingestion.

## Known traps
- nba_api header stripping → timeouts. Verify `User-Agent`/`Referer` present.
- Rate limit is real → resumable checkpointed ingestion is mandatory.
- Yahoo OAuth is 3-legged → cache the refresh token.
- %-cat z-score trap → impact-weight FG%/FT% by attempts, not raw rates.

## Project Structure
- `ingest.py` — CLI entry: `backfill` / `update` / `status`.
- `update.bat` — one-click nightly refresh.
- `fbball/` — package:
  - `db.py` — DuckDB schema, idempotent upsert, checkpoint + season-completion.
  - `nba_source.py` — thin nba_api wrapper (the only network module): retry + backoff.
  - `transform.py` — pure raw→schema column mapping.
  - `seasons.py` — NBA season-label helpers.
  - `ingest.py` — orchestration: backfill (resumable) + update (incremental).
- `tests/` — 28 pytest tests (`python -m pytest tests/ -q`).
- `data/fbball.duckdb` — the store (git-ignored, rebuildable).
- `docs/BUILD-SPEC.md` — full original build spec.

## Status
- **Component 1 — DONE & verified.** 105k game-log rows, 4 seasons.
- **Reference tables — DONE & verified.** 30 teams + 5,130 players. 877/877 game-log players join losslessly.
- **Analytics views — DONE & verified.** `player_season_stats`, `player_recent_form` (live, volume-weighted %).
- **Component 2 (slice 1) — Yahoo league pull LIVE.** `python ingest.py yahoo`. Ported `fbball/yahoo_client.py`; creds gitignored. League `466.l.79957`; my team `slimpickens`. Stored in `yahoo_teams`/`yahoo_roster`.
- **Player-ID bridge LIVE.** `fbball/bridge.py`; 157/157 rosters linked to NBA stats.
- **Component 3 — valuation engine DONE.** `python value.py` (9-cat z-scores, impact-weighted %, punt-aware). `fbball/valuation.py`.
- **Component 4 (waivers) DONE.** `python ingest.py freeagents` + `python waivers.py`. Marginal-value-to-needs ranking. `fbball/recommend.py`.
- **Next:** start/sit (games-per-week) + trade analyzer. See README/TODO.

## Environment Variables
- Yahoo: `YAHOO_CLIENT_ID`, `YAHOO_CLIENT_SECRET` (Component 2, not yet). Never commit.

## Skills & Protocols
- **Security Audit**: `../../_skills/security-audit/SKILL.md` — run before any deploy.
