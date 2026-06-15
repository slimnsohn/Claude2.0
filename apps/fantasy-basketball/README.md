# Fantasy Basketball Decision Engine

A Yahoo H2H 9-cat decision engine. **Component 1 (the NBA data lake) is built.**
Everything downstream reads from this store instead of hammering the NBA API.

## What's working now

A local, queryable database of every NBA player's game-by-game stat line across
the last 4 seasons (~105k rows), stored in DuckDB. Refreshable nightly.

## Setup (once)

```bash
pip install -r requirements.txt
```

## Offseason refresh (the once-a-year workflow)

Run this each offseason (≈April–September) to pull the season that just
finished and refresh player/position data, then build your board:

```bash
python ingest.py prep              # pulls last season's logs + reference data
python draft.py                    # board auto-uses the latest season — no year to edit
```

That's it. `prep` targets the just-completed season automatically, and every
analysis tool defaults to the latest season in your data lake.

## Use it

```bash
python ingest.py backfill          # one-time: load the last 4 seasons
python ingest.py backfill --seasons 6   # ...or more history
python ingest.py reference         # load team + player reference tables (positions, teams)
python ingest.py yahoo             # pull your Yahoo league rosters (all 10 teams)
python ingest.py freeagents        # pull the league's free-agent pool
python ingest.py update            # nightly: pull the current season's new games
python ingest.py status            # what's in the store right now
```

Or just double-click **`update.bat`** to refresh today's games.

## Value players (9-cat z-scores)

```bash
python value.py                    # top 30 overall (season value)
python value.py --mine             # value YOUR roster vs the league pool
python value.py --punt FT_PCT TOV  # punt build: re-rank ignoring those cats
python value.py --source recent    # rank by current form (last 15 games)
```

Values are z-scores vs the qualifying pool. FG%/FT% use the volume-weighted
**impact** method (not raw percentage). Punting a category re-ranks for that
build — e.g. punting FT%+TO lifts a Gobert-type big who's elite everywhere else.
Engine: `fbball/valuation.py`.

## Waiver pickups (ranked by YOUR needs)

```bash
python ingest.py freeagents        # pull the FA pool first (daily)
python waivers.py                  # ranked pickups that fill your weak cats
python waivers.py --punt FT_PCT TOV
```

Free agents are ranked by **marginal value to your roster**, not raw value:
your weakest category gets the highest weight, your strongest gets zero. A steal
specialist who fills a category you're losing beats a higher-raw-value scorer
who piles onto a category you're already winning. The output shows both `RAW`
(overall value) and `FIT` (needs-weighted) so the difference is visible.
Engine: `fbball/recommend.py`.

## Yahoo league history (a fixed, separate data lake)

```bash
python ingest.py history     # walk the renew chain, pull all 16 past seasons (once)
python ingest.py owners      # rebuild + show canonical owner identity (no API calls)
```

Immutable `yh_*` tables capturing every season back to 2010:
- `yh_seasons` — each season's league_key, name, team count, dates
- `yh_teams` — teams + **owners keyed by email** (owners change & rename; email is stable)
- `yh_standings` — `final_rank` (reflects playoffs), `playoff_seed` (regular-season seed),
  and a derived `regular_season_rank` for **all** teams (from W-L record; validated to
  match Yahoo's seed exactly)
- `yh_draft` — every draft pick (player names resolved where the player stayed rostered)
- `yh_final_roster` — end-of-season rosters
- `yh_owner_identity` — derived canonical owner per team-season. Resolves the
  same person across team renames AND email changes/blanks by linking
  team-seasons that share any non-blank signal (team name, email, or nickname),
  prioritizing team-name continuity. 22 true owners over the league's history.

This is separate from the live Yahoo tables (`yahoo_roster`/`yahoo_free_agents`,
which refresh) — history never changes, so it's pulled once. Engine:
`fbball/yahoo_history.py`.

## Draft board

```bash
python draft.py                    # punt-aware value, grouped into tiers
python draft.py --pos C            # positional run (centers only)
python draft.py --punt FT_PCT TOV  # board for a punt build (re-tiers)
python draft.py --gap 1.0          # coarser tiers
```

Players ranked by 9-cat value, grouped into **tiers** at value cliffs (a new
tier starts where value drops by more than `--gap`), with **positional rank**
(`C3` = 3rd-best center, grouped by primary position) for scarcity. Punt builds
re-rank and re-tier — e.g. punting FT%+TO lifts Giannis into the top tier.
Engine: `fbball/draft.py`.

Every command is **safe to re-run**. Writes are idempotent on
`(player_id, game_id)`, so you can never create duplicates. Historical seasons
are marked complete and never re-pulled; only the in-progress season refreshes.
A killed run picks up exactly where it stopped.

## Where the data lives

`data/fbball.duckdb` — a single file, git-ignored (rebuild it anytime from the
commands above). Query it directly:

```python
import duckdb
con = duckdb.connect("data/fbball.duckdb")
con.execute("SELECT player_name, AVG(pts) FROM game_logs "
            "WHERE season='2025-26' GROUP BY player_name ORDER BY 2 DESC LIMIT 10").df()
```

## Data organization

One DuckDB file (`data/fbball.duckdb`), three isolated namespaces — they never
share a table, so no operation in one domain can corrupt another's raw data:

| Prefix | Domain | Mutability |
|--------|--------|------------|
| `game_logs`, `players`, `teams` | NBA stats (the data lake) | refreshable |
| `yahoo_*` | live Yahoo (rosters, free agents) | snapshot, re-pulled |
| `yh_*` | Yahoo league **history** | fixed, pulled once |

The Yahoo writers (`replace_history`, the snapshot upserts) only ever touch
their own tables — `replace_history` rejects any non-`yh_` table by name — so
the NBA raw data is structurally protected from the fantasy side.

## Schema

**Tables.** `game_logs` — raw per-game lines (the source of truth, 9-cat stats
+ FG/FT makes & attempts; ~105k rows). `players` — every player (5,130): id,
name, active flag, current NBA position (G/F/C) + team for those on rosters;
joins to `game_logs` losslessly on `player_id`. `teams` — 30 NBA teams.
`completed_seasons` / `ingest_state` — ingestion bookkeeping.
(`players.positions` stays empty until Yahoo eligibility joins in — Component 2.)

**Yahoo league tables.** `yahoo_teams` — the 10 fantasy teams (your team flagged
`is_my_team`). `yahoo_roster` — every team's current roster: player, NBA team,
Yahoo eligibility, injury status, and `nba_player_id` — the **bridge** to the
stats lake, filled by the name matcher (`fbball/bridge.py`: accent/suffix/
punctuation-normalized, collisions resolved by active-player + team, nicknames
via an alias map; unmatched left NULL, never force-matched). The `yahoo` command
auto-bridges. Credentials live in gitignored `yahoo_creds.json` /
`yahoo_token.json` (reused from a prior build; never committed). League:
`466.l.79957` "The Best Time of Year" (9-cat H2H).

```python
# Your roster, with live season stats — joined through the bridge:
con.execute("""
  SELECT r.player_name, s.ppg, s.rpg, s.apg, s.fg_pct
  FROM yahoo_roster r JOIN yahoo_teams t USING (team_key)
  JOIN player_season_stats s
    ON s.player_id = r.nba_player_id AND s.season='2025-26'
  WHERE t.is_my_team ORDER BY s.ppg DESC
""").df()
```

**Analytics views** (always live — recompute from `game_logs`, no refresh step):
- `player_season_stats` — one row per (player, season, season_type): games
  played, per-game rates for all 9 cats, and **volume-weighted** FG%/FT% (total
  makes ÷ total attempts — *not* the average-of-percentages trap).
- `player_recent_form` — last 15 games of the current season per player: the
  same rates, for projection / "who's hot" reads.

```python
con.execute("SELECT full_name, ppg, fg_pct FROM player_season_stats "
            "WHERE season='2025-26' AND gp>=40 ORDER BY ppg DESC LIMIT 10").df()
con.execute("SELECT full_name, ppg FROM player_recent_form "
            "ORDER BY ppg DESC LIMIT 10").df()   # current form
```

## Tests

```bash
python -m pytest tests/ -q
```

## What's next

See `TODO.md`. Next up: Component 2 (Yahoo league pull) and Component 3
(valuation engine), both reading from this store.

Full design rationale: `docs/BUILD-SPEC.md`.
