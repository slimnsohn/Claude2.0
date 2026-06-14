# TODO — Fantasy Basketball Decision Engine

> Update manually. This file persists across sessions.

## Now

- [ ] Component 4 (start/sit surface): weekly matchup + games-per-week pull, then optimize the lineup to maximize expected category wins.

## Next

- [ ] Trade analyzer (net category-value swing for both sides, punt-aware).
- [ ] Draft board (punt-build-aware tiers + positional scarcity) — seasonal.

## Backlog

- [ ] Component 4: decision surfaces (waivers, start/sit, trades, draft).
- [ ] Schedule `update.bat` nightly (Task Scheduler) during the season.
- [ ] Optional: extend history back to ~2015 for aging-curve modeling (store, don't pollute current baselines).

## Done

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
