# TODO — Fantasy Basketball Decision Engine

> Update manually. This file persists across sessions.

## Now

- [ ] Player-ID bridge: match `yahoo_roster.player_name` → NBA `players.player_id` (handle Jr./accents/nicknames, e.g. "Bones Hyland" = "Nah'Shon Hyland"). The join the whole decoupled design hinges on.

## Next

- [ ] Yahoo free agents / waiver pool pull (the available-player universe).
- [ ] Component 3: valuation engine — port `zscore.py`/`categories.py` onto the live views (z-scores → punt-aware → impact-weighted %-cats). Reads `player_season_stats` / `player_recent_form`.

## Backlog

- [ ] Component 4: decision surfaces (waivers, start/sit, trades, draft).
- [ ] Schedule `update.bat` nightly (Task Scheduler) during the season.
- [ ] Optional: extend history back to ~2015 for aging-curve modeling (store, don't pollute current baselines).

## Done

- [x] **Component 2 (slice 1) — Yahoo league pull (LIVE & VERIFIED).** `python ingest.py yahoo`.
  - Reused prior working creds + refresh token (no re-registration). Ported proven `fbball/yahoo_client.py` (raw OAuth2 + Yahoo-JSON parsers).
  - Stored all 10 teams + 157 roster spots into `yahoo_teams` / `yahoo_roster`; your team `slimpickens` auto-flagged. Eligibility + injury status captured. Roster stored as a snapshot (drops disappear on re-pull).
  - Confirmed league settings live: 9 cats (FG%,FT%,3PTM,PTS,REB,AST,STL,BLK,TO), roster PG/SG/G/SF/PF/F/C×2/Util×2/BN×5/IL+. League `466.l.79957`.
- [x] **Analytics views (COMPLETE & VERIFIED).** SQL views, always live (no refresh step).
  - `player_season_stats` — per player/season: GP, per-game rates for 9 cats, volume-weighted FG%/FT% (total makes ÷ attempts, not avg-of-pcts). 2,262 rows across 4 seasons.
  - `player_recent_form` — last 15 games of current season per player (582 rows). Surfaces form divergence (Luka 37.1 last-15 vs 33.5 season).
  - Validated against live store: matches verified season averages exactly. 48 tests pass.
- [x] **Player & team reference tables (COMPLETE & VERIFIED).** `python ingest.py reference`.
  - 30 teams + 5,130 players (id, name, active flag) from nba_api bundled static data.
  - 530 active players enriched with NBA position (G/F/C) + current team from 30 roster calls.
  - Gap closed: 27 players in game_logs but missing from the static list recovered from the logs — now 877/877 game-log players join losslessly. Missing position/team left NULL, never faked.
- [x] **Component 1 — NBA data lake (COMPLETE & VERIFIED).** `ingest.py` + DuckDB store.
  - 105,252 game-log rows across 4 seasons (2022-23 … 2025-26), one call per season.
  - Idempotent upsert on (player_id, game_id) — re-runs never duplicate.
  - Resumable in any order via `completed_seasons` (historical seasons immutable; current re-pulls).
  - Rate-limited (0.7s) + exponential-backoff retry on the NBA endpoint.
  - CLI: `backfill` / `update` / `status`, plus one-click `update.bat`.
  - 28 unit tests passing; spot-checked star lines (Luka 33.5 PPG, SGA 31.1) — data correct.
