# Fantasy Basketball Decision Engine — Build Spec

**League type:** Yahoo H2H Categories (9-cat: FG%, FT%, 3PM, PTS, REB, AST, STL, BLK, TO)
**Scope:** Historical data lake → valuation engine → decision surfaces (draft, waivers, start/sit, trades)
**Hosting:** `help.sohn` Google account for any Apps Script / web surfaces
**Build philosophy:** Data layers stable first, app layers disposable. Lock the ingestion + storage before touching the model.

---

## Architecture overview

```
[Ingestion]  nba_api + Yahoo API  ──►  [Storage]  DuckDB / Parquet
                                              │
                                              ▼
                                    [Valuation engine]  per-cat z-scores,
                                    punt-aware, volume-weighted %-cats
                                              │
                                              ▼
              [Decision surfaces]  draft board · waivers · start/sit · trade analyzer
```

Two independent data sources that must NOT be conflated:
1. **NBA stats** (`nba_api`) — the league-wide player performance universe. Public, no auth, rate-limited.
2. **Your Yahoo league** (Yahoo Fantasy API) — your rosters, free agents, matchups, settings. OAuth2, auth-gated.

The NBA stats layer is the historical aggregation problem. Build it first and standalone — it has value regardless of the Yahoo integration, and the Yahoo OAuth dance shouldn't block stats ingestion.

---

## Component 1 — Historical data aggregation (BUILD FIRST)

### Goal
A local, queryable store of every player's game-by-game stat line across N seasons, refreshable nightly during the season, so the valuation engine reads from disk instead of hammering the NBA API on every calculation.

### Source & endpoints (`nba_api`)
- **Bulk backfill:** `PlayerGameLogs` (plural) — pulls the entire league's game logs for one season in a single call. This is the workhorse for historical loading. Loop seasons, one call each.
  ```python
  from nba_api.stats.endpoints import PlayerGameLogs
  df = PlayerGameLogs(
      season_nullable='2024-25',
      season_type_nullable='Regular Season'
  ).get_data_frames()[0]
  ```
- **Incremental/targeted:** `PlayerGameLog` (singular) for a single player when filling gaps.
- **Static reference:** `nba_api.stats.static.players` / `teams` for the player↔ID↔team mapping table.
- **Advanced (optional later):** `BoxScoreAdvancedV3`, usage rates, etc. — defer until base cats work end to end.

### Rate limiting — the real constraint
NBA.com throttles aggressively and bans IPs that hammer it. The ingestion layer MUST:
- Sleep ~0.6–1.0s between calls (the community-standard floor).
- Set proper headers (the library does this, but verify a `User-Agent` and `Referer` are present — stripped headers are the #1 cause of timeouts).
- Use a retry wrapper with exponential backoff on `ReadTimeout` / 429.
- Be **resumable** — write a checkpoint (last completed season + date) so a killed run picks up where it stopped rather than re-pulling everything.
- Run the full historical backfill once, off-hours, then switch to incremental nightly pulls of only games since the last checkpoint.

### Storage — recommendation: DuckDB
Use **DuckDB** over SQLite or raw Parquet. Rationale:
- Columnar + vectorized — z-score aggregations across the full player pool are exactly its sweet spot, and they'll be fast.
- Reads/writes Parquet natively, single-file database, zero server.
- This matches the framework in the `Jon-Becker/prediction-market-analysis` repo you already flagged, so the pattern is familiar.

Schema (start minimal, widen later):
```sql
-- raw game logs, append-only, the source of truth
CREATE TABLE game_logs (
    player_id      INTEGER,
    player_name    VARCHAR,
    team           VARCHAR,
    season         VARCHAR,      -- '2024-25'
    season_type    VARCHAR,      -- 'Regular Season' | 'Playoffs'
    game_id        VARCHAR,
    game_date      DATE,
    min            DOUBLE,
    fgm DOUBLE, fga DOUBLE,
    ftm DOUBLE, fta DOUBLE,
    fg3m           DOUBLE,
    pts DOUBLE, reb DOUBLE, ast DOUBLE,
    stl DOUBLE, blk DOUBLE, tov DOUBLE,
    PRIMARY KEY (player_id, game_id)
);

-- player reference / current team / position eligibility
CREATE TABLE players (
    player_id   INTEGER PRIMARY KEY,
    full_name   VARCHAR,
    is_active   BOOLEAN,
    positions   VARCHAR        -- Yahoo eligibility, joined in later
);

-- ingestion checkpoint
CREATE TABLE ingest_state (
    source      VARCHAR,        -- 'nba_game_logs'
    last_season VARCHAR,
    last_date   DATE,
    updated_at  TIMESTAMP
);
```

The `PRIMARY KEY (player_id, game_id)` gives idempotent upserts — re-running ingestion can't create duplicate rows. Use DuckDB `INSERT ... ON CONFLICT DO NOTHING` (or stage + anti-join).

### How much history?
For valuation baselines you want recent enough to reflect the current league environment but enough sample for stable z-score distributions. **3–4 most recent seasons** is the practical sweet spot. Pull more (back to ~2015) only if you later want trend/aging-curve modeling — store it but don't let it pollute the current-season baselines.

### Deliverable for this component
A standalone `ingest.py` that: backfills N seasons, is resumable, rate-limits politely, and can be cron'd nightly for incremental updates. Verify row counts against a known game (e.g., spot-check a star's game line vs. Basketball Reference) before trusting it downstream.

---

## Component 2 — Yahoo league integration

### Auth (the fiddly part — budget ~1 hr)
- Register an app at the Yahoo Developer portal → get client ID/secret.
- 3-legged OAuth2: one-time browser consent → cache the **refresh token** (long-lived) so you never re-consent.
- `yahoo_fantasy_api` Python wrapper handles token refresh and endpoint calls.

### What to pull
- League settings (confirm the exact 9 cats and roster slots — don't assume).
- Your roster + all opponent rosters.
- Free agents / waiver pool.
- Weekly matchup schedule + each NBA team's games-per-week (critical for start/sit).
- Position eligibility per player → joins into the `players.positions` column.

### Stabilize before modeling
Verify a live pull of your actual roster and free agents against what you see in the Yahoo app. Auth + correct league data is the dependency for every decision surface.

---

## Component 3 — Valuation engine (the modeling)

### Per-category z-scores (9-cat)
For each cat, standardize a player's per-game rate against the rostered player pool, then sum to a total value. Two non-negotiable refinements:

**Punt-aware valuation.** Re-rank under each punt build (e.g., punt FT%+TO to chase bigs; punt FG%+TO to chase guards). The optimal target list changes completely by build — this is the single highest-value feature vs. Hashtag Basketball. Implement as: zero out the punted cats, recompute totals, re-sort.

**Volume-weighted percentage cats.** FG% and FT% must be weighted by attempts, not treated as raw rates. The standard fix is *impact* / *marginal* percentage value:
```
ft_impact = (player_ft%  - league_ft%) * player_fta
fg_impact = (player_fg%  - league_fg%) * player_fga
```
then z-score the *impact*, not the raw percentage. A 90% FT shooter on 2 attempts is near-zero impact; on 8 attempts it's real. Naive z-scores get this badly wrong — known trap.

### Projections, not just season-to-date
Read game logs from DuckDB and project rather than echo totals: recent-weighted rates (e.g., last 15 games weighted over season), with minutes as the stabilizer. Keep projection logic in its own module so it's swappable.

---

## Component 4 — Decision surfaces

- **Draft board** — punt-build-aware rankings, positional scarcity, tiers.
- **Waiver pickups** — rank free agents by *marginal* value to YOUR roster's current category needs (not raw value). A player who helps your weak cats outranks a higher-raw-value player who piles onto a cat you're already winning.
- **Start/sit** — weekly optimization counting games-per-week per player (the thing casual tools handle worst). Maximize expected category wins given your matchup.
- **Trade analyzer** — net category-value swing for both sides, with punt-build awareness and a "does this actually change which cats I win" read on the matchup.

---

## Build order (dependency-correct)

1. **Data aggregation** — `ingest.py` + DuckDB store, backfill 3–4 seasons, verify, set up nightly incremental. *(Nothing depends on Yahoo — start here.)*
2. **Yahoo auth + league pull** — stabilize, verify against the app.
3. **Valuation engine** — z-scores → punt-aware → volume-weighted %-cats, reading from DuckDB.
4. **Decision surfaces** — waivers/start-sit first (highest in-season value), then trade analyzer, then draft board (seasonal).

## Notes / gotchas captured
- nba_api header stripping → timeouts. Verify headers present.
- Rate limit is real; resumable checkpointed ingestion is mandatory, not optional.
- Yahoo OAuth is 3-legged; cache the refresh token.
- %-cat volume weighting is the classic z-score trap — do impact-weighting.
- Keep the NBA stats layer and Yahoo layer decoupled; join only at the player_id level.
