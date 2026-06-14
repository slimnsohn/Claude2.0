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

## Use it

```bash
python ingest.py backfill          # one-time: load the last 4 seasons
python ingest.py backfill --seasons 6   # ...or more history
python ingest.py reference         # load team + player reference tables (positions, teams)
python ingest.py yahoo             # pull your Yahoo league rosters (all 10 teams)
python ingest.py update            # nightly: pull the current season's new games
python ingest.py status            # what's in the store right now
```

Or just double-click **`update.bat`** to refresh today's games.

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

## Schema

**Tables.** `game_logs` — raw per-game lines (the source of truth, 9-cat stats
+ FG/FT makes & attempts; ~105k rows). `players` — every player (5,130): id,
name, active flag, current NBA position (G/F/C) + team for those on rosters;
joins to `game_logs` losslessly on `player_id`. `teams` — 30 NBA teams.
`completed_seasons` / `ingest_state` — ingestion bookkeeping.
(`players.positions` stays empty until Yahoo eligibility joins in — Component 2.)

**Yahoo league tables.** `yahoo_teams` — the 10 fantasy teams (your team flagged
`is_my_team`). `yahoo_roster` — every team's current roster: player, NBA team,
Yahoo eligibility, injury status, and `nba_player_id` (the bridge to the stats
lake — filled by the name matcher, next step). Credentials live in gitignored
`yahoo_creds.json` / `yahoo_token.json` (reused from a prior build; never
committed). League: `466.l.79957` "The Best Time of Year" (9-cat H2H).

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
