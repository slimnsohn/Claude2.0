# TODO — Fantasy Basketball Decision Engine

> Update manually. This file persists across sessions.

## Now

- [ ] (Open) Pick the next thing when needed — full pipeline, history lake, projections, and live draft are all done.

## Next

- [ ] Optional: port synergy/roster-analyzer (archetypes, complementary pairings) from the old project if in-season tools ever wanted.
- [ ] Optional: external ranking benchmark (Basketball Monster) for projection validation.

## Backlog

- [ ] Component 4: decision surfaces (waivers, start/sit, trades, draft).
- [ ] Schedule `update.bat` nightly (Task Scheduler) during the season.
- [ ] Optional: extend history back to ~2015 for aging-curve modeling (store, don't pollute current baselines).

## Done

- [x] **Web UI — BUILT & VERIFIED.** `start.bat` → http://127.0.0.1:5050.
  - Flask (`app.py`, read-only) + thin JSON API (`fbball/webapi.py`) over the tested engine; vanilla-JS single page (`web/`) with workspace base.css + chat widget. Design spec: `docs/web-ui-design.md`.
  - 6 tabs: Overview, Players (accent-insensitive search + per-season accordion), Rankings (source/punt/pos), Draft cockpit (projected tiered board + live tracking + needs panel), League (champions/owners/standings/draft/rosters), Update.
  - **Update tab**: refresh the whole lake from the browser (one button or per-step checkboxes) with live SSE progress; runs `ingest.py refresh` (logs/reference/ages/history/live) as an isolated subprocess. The write path is the only thing that mutates data; serving stays read-only.
  - Verified live against real data; ~20 API/route tests. Google-clean styling.
- [x] **Projection engine + live draft assistant — BUILT & VERIFIED (ported from old project, upgraded).**
  - Ages pulled in bulk (`LeagueDashPlayerBioStats`, 1 call/season) → `player_bio`; `python ingest.py bios` (folded into `prep`).
  - `fbball/projections.py`: next-season per-game projection. Model upgrades over the old code: age handled as growth/decline RATIO (curve(target)/curve(recent)) so young players project up; sample-weighted by GP; recency-weighted (last 3 seasons). Wired as `--source projection`; draft board now defaults to it.
  - `fbball/livedraft.py` + `livedraft.py`: interactive draft-day assistant. Tracks picks, best-available by projected value, needs-weighted once you have picks, accent/typo-tolerant name resolution. Verified live: 851 players, projected 2026-27 board (Wemby #1), needs view shifts after picks.
- [x] **Yahoo league history lake — BUILT & VERIFIED.** `python ingest.py history`.
  - Walks the renew chain back to 2010; 16 seasons, 168 team-seasons, 2,516 draft picks, 2,554 final-roster spots.
  - Tables: yh_seasons, yh_teams (owners by email — 22 distinct owners), yh_standings (final_rank vs playoff_seed vs derived regular_season_rank), yh_draft, yh_final_roster. `fbball/yahoo_history.py`.
  - Validated: derived regular_season_rank matches Yahoo playoff_seed exactly; 2024 champ was a 5-seed. Draft names 100% resolved (batched player lookup fills drafted-then-dropped players).
  - Data organization documented: one DuckDB file, isolated namespaces (NBA `game_logs`/`players`/`teams`, live `yahoo_*`, history `yh_*`); `replace_history` rejects non-`yh_` tables so NBA raw data is structurally protected.
  - Canonical owner identity (`yh_owner_identity`, `python ingest.py owners`): union-find over team-seasons sharing any non-blank signal (team name / email / nickname), team-name continuity prioritized. 22 true owners; folds name-changers (slimpickens 11 names→1) and bridges blank-email years (LetsBall).
- [x] **Draft board — COMPLETE & VERIFIED.** `python draft.py`.
  - Punt-aware 9-cat value → tiers (gap-based value cliffs) → positional rank by primary position (`fbball/draft.py`).
  - `--pos`, `--punt`, `--gap` flags. Validated live: Jokić Tier 1; punt FT%+TO lifts Giannis into the top tier. 86 tests pass.
- [x] **Component 4 (waivers surface) — COMPLETE & VERIFIED.** `python ingest.py freeagents` then `python waivers.py`.
  - Pulls + bridges the FA pool (live: 200/200 matched), stores in `yahoo_free_agents`.
  - Ranks FAs by *marginal* value to my category needs (`fbball/recommend.py`): weakest cat weight 1.0, strongest 0.0, punts 0. Shows RAW vs FIT.
  - Validated live: my needs = TO + STL; surfaced steal specialists (Thybulle RAW 1.05 but FIT-ranked #3). 79 tests pass.
- [x] **Component 3 — valuation engine (COMPLETE & VERIFIED).** `python value.py`.
  - 9-cat z-scores; FG%/FT% volume-weighted (impact method); TOV inverted; punt-aware.
  - `fbball/valuation.py` (pure `compute_values` + `rank_from_db`); reads season or recent-form views.
  - `value.py` CLI: overall / `--mine` / `--punt` / `--source recent`.
  - Validated on live data: Jokić #1, Wemby #2, SGA #3 (correct elite 9-cat order); punting FT%+TO lifts Gobert #91→#29. 69 tests pass.
- [x] **Player-ID bridge (LIVE & VERIFIED).** `fbball/bridge.py`, auto-run by `yahoo`.
  - 157/157 roster players matched to NBA player_ids; 0 unmatched.
  - Normalized names (accents/suffixes/punctuation); collisions (Gary Trent Jr., Jabari Smith Jr.) resolved by active-player preference; alias map for nicknames; unmatched left NULL.
  - Your roster now joins to live stats (Brunson 26 PPG, Wemby 25/11.5/3.1 blk).
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
