# Odds Pipeline — Design

**Date:** 2026-05-24
**Project:** `apps/odds-pipeline`
**Intent:** Rock-solid infrastructure to store historical and grab new odds + results data — full game and derivative periods (quarters, halves, periods, innings) — across NBA, NFL, NHL, MLB, NCAAB, NCAAF.

---

## 1. Goals & Scope

**Primary goal:** A multi-sport data layer that pulls game-event lists + closing odds from The Odds API, fetches final + per-segment scores from sport-specific official feeds, archives every raw API response, and derives a queryable SQLite database that downstream modeling projects read.

**v1 sample run:** Pull a handful of games per sport (~10/sport, `--limit 10`) from January 2025 across NBA + NFL + NHL + NCAAF to validate the framework end-to-end.

Credit budget (optimistic, assumes per-event endpoint costs 1 credit/market/region):
- NBA: 10 games × 7 markets × 2 regions = 140
- NFL: 10 × 7 × 2 = 140
- NHL: 10 × 5 × 2 = 100
- NCAAF: 10 × 7 × 2 = 140
- Event-list calls (one per sport per day): ~124
- **Total: ~640 credits.** If per-event endpoint actually costs 10/market/region (bulk-endpoint rate), multiply by 10 → ~6,400. Either way fits in 20K/month with significant headroom.

**v1 explicitly out of scope:**
- Live/in-play odds collection
- Alternate-line markets (`alternate_spreads`, `alternate_totals`) — easy add later
- Multi-snapshot line-movement tracking — single closing snapshot only
- Modeling, EV calculation, or backtesting — this is the data layer only
- MLB and NCAAB sample odds pulls (adapters built, no odds pulled in sample run — MLB offseason, NCAAB too credit-expensive at peak)

**Sports supported by v1 framework (all six get adapters):** NBA, NFL, NHL, MLB, NCAAB, NCAAF.

---

## 2. Key Findings From API Recon

| Question | Finding |
|---|---|
| Historical odds depth | From 2020-06-06 (~5+ seasons for NBA, 6 for NFL) |
| Historical for period markets (quarters/halves) | Only since **2023-05-03** — ~2 NBA + ~2 NFL seasons available |
| Snapshot frequency | 10-min intervals 2020-06 → 2022-09; 5-min since |
| Closing-line semantics | "Closest snapshot ≤ provided date" → query with `commence_time - 5 min` |
| Pinnacle | Supported (`pinnacle`, region `eu`). **Open question: does Pinnacle return segment markets?** Likely light on derivatives. Will be revealed by first ~10 games of sample. |
| Other sharp books | Circa Sports, BookMaker.eu: **NOT supported** |
| Soft books | DraftKings, FanDuel, BetMGM all in `us` region |
| Scores endpoint | Rolling 3 days only, no historical, no per-segment data shown → **scores must come from sport-specific official feeds** |
| Quarter market keys | `h2h_q1..q4`, `spreads_q1..q4`, `totals_q1..q4` — same keys NBA & NFL |
| Half market keys | `h2h_h1/h2`, `spreads_h1/h2`, `totals_h1/h2` |
| Pricing | $30 = 20K credits/month (current plan) |
| Historical event endpoint cost | Docs ambiguous; reads as 1 credit/market/region. **Will be confirmed empirically via `x-requests-used` response header on first call.** |
| Bulk historical odds endpoint | 10 credits × markets × regions — too expensive for our use case; per-event is the right tool |

---

## 3. Architecture

```
apps/odds-pipeline/
├── CLAUDE.md
├── start.bat                    # python -m odds_pipeline <cmd>
├── cli.py                       # init | pull-odds | pull-results | build | status
├── odds_pipeline/
│   ├── __main__.py
│   ├── config.py                # SPORT_MARKETS, segment shapes, env keys
│   ├── odds_source/
│   │   ├── the_odds_api.py
│   │   └── client.py            # rate limiting, credit tracking via x-requests-used, retries
│   ├── results_sources/
│   │   ├── base.py              # ResultsAdapter ABC + GameResult dataclass
│   │   ├── nba.py               # nba_api
│   │   ├── nfl.py               # nfl_data_py
│   │   ├── nhl.py               # NHL Stats API (direct HTTP)
│   │   ├── mlb.py               # MLB-StatsAPI
│   │   ├── ncaab.py             # sportsdataverse-py or ESPN scoreboard JSON
│   │   └── ncaaf.py             # cfbd-api
│   ├── archive/                 # writes raw JSON
│   ├── store/
│   │   ├── schema.sql
│   │   ├── migrate.py
│   │   └── derive.py            # raw JSON → SQLite tables
│   └── identity/
│       ├── matcher.py
│       └── aliases/{sport}.json # team-name normalization tables per sport
├── data/
│   ├── raw/odds/{sport}/{date}/{event_id}__{snapshot_time}.json
│   ├── raw/results/{sport}/{date}/{game_id}.json
│   └── odds_pipeline.db
├── tests/
└── TODO.md
```

**Module boundaries (the rules of isolation):**
- `odds_source/` knows nothing about results.
- `results_sources/` knows nothing about odds.
- Both write to `archive/` only. Neither writes to the SQLite DB directly.
- `store/derive.py` is the only place that reads raw JSON and writes derived tables.
- `identity/` is the only place that handles cross-source game-ID matching and team-name canonicalization.

**Why this shape:** raw is the source of truth and re-derivable. SQLite is the working surface for modeling. Adding a 7th sport later is one new adapter file. Schema bugs are fixed by editing `derive.py` and re-running `build` — no re-pull needed.

---

## 4. Database Schema

Six tables. Long format (one row per side per market per snapshot) — flexible for both single-snapshot historical and future multi-snapshot collection.

```sql
-- 1. Reference: which segments exist per sport
CREATE TABLE segment_types (
  sport         TEXT,           -- NBA, NFL, NHL, MLB, NCAAB, NCAAF
  segment_key   TEXT,           -- FULL, Q1, H1, P1, INN1, F5, OT1, SO, ...
  kind          TEXT,           -- full / quarter / half / period / inning / inning_range / overtime / shootout
  order_idx     INTEGER,        -- for chronological sorting
  PRIMARY KEY (sport, segment_key)
);
-- Seeded at install time. Examples:
--   NBA  : FULL, Q1, Q2, Q3, Q4, H1, H2, OT1, OT2, OT3, OT4
--   NFL  : FULL, Q1, Q2, Q3, Q4, H1, H2, OT1
--   NHL  : FULL, P1, P2, P3, OT1, SO
--   MLB  : FULL, INN1..INN9 (+ extras as needed), F5
--   NCAAB: FULL, H1, H2, OT1, OT2, ...
--   NCAAF: FULL, Q1, Q2, Q3, Q4, H1, H2, OT1, OT2, ...

-- 2. Reference: sportsbooks
CREATE TABLE bookmakers (
  key      TEXT PRIMARY KEY,    -- 'pinnacle', 'draftkings', 'fanduel', 'betmgm', ...
  title    TEXT,
  region   TEXT,                -- us, eu, uk, au
  sharp    INTEGER              -- 1 for Pinnacle (and any future sharp books), else 0
);

-- 3. Games: one row per game, canonical across odds and results
CREATE TABLE games (
  game_id                  TEXT PRIMARY KEY,   -- '{sport}:{yyyymmdd}:{away}@{home}' e.g. 'NBA:20250115:LAL@BOS'
  sport                    TEXT NOT NULL,
  commence_time            TEXT NOT NULL,      -- ISO-8601 UTC
  home_team                TEXT NOT NULL,      -- canonical names from identity/aliases/{sport}.json
  away_team                TEXT NOT NULL,
  season                   INTEGER,
  season_type              TEXT,               -- regular | playoff | preseason
  odds_api_event_id        TEXT UNIQUE,        -- for re-querying
  results_source_game_id   TEXT,               -- sport-specific official ID
  created_at               TEXT,
  updated_at               TEXT
);
CREATE INDEX idx_games_sport_date ON games(sport, commence_time);

-- 4. Odds: long format, one row per (game, book, market, side, snapshot)
CREATE TABLE odds_snapshots (
  snapshot_id      INTEGER PRIMARY KEY,
  game_id          TEXT NOT NULL REFERENCES games(game_id),
  bookmaker_key    TEXT NOT NULL REFERENCES bookmakers(key),
  segment_key      TEXT NOT NULL,              -- FULL, Q1, H1, P1, F5, ...
  market_type      TEXT NOT NULL,              -- 'h2h' | 'spreads' | 'totals'
  side             TEXT NOT NULL,              -- 'home'|'away' for h2h/spreads; 'over'|'under' for totals
  line             REAL,                       -- spread or total value; NULL for h2h
  price_american   INTEGER NOT NULL,
  price_decimal    REAL,
  snapshot_time    TEXT NOT NULL,              -- when the snapshot was captured (ISO UTC)
  is_close         INTEGER NOT NULL DEFAULT 0, -- 1 if this is the closing snapshot for this game/book/market/segment/side
  raw_archive_path TEXT NOT NULL               -- 'data/raw/odds/NBA/2025-01-15/{event_id}__{snapshot_time}.json'
);
CREATE INDEX idx_odds_game ON odds_snapshots(game_id);
CREATE INDEX idx_odds_close ON odds_snapshots(game_id, is_close) WHERE is_close = 1;

-- 5. Scores: long format, one row per (game, segment)
CREATE TABLE scores (
  game_id          TEXT NOT NULL REFERENCES games(game_id),
  segment_key      TEXT NOT NULL,
  home_score       INTEGER NOT NULL,
  away_score       INTEGER NOT NULL,
  raw_archive_path TEXT NOT NULL,
  PRIMARY KEY (game_id, segment_key)
);

-- 6. Ingest observability
CREATE TABLE ingest_runs (
  run_id         INTEGER PRIMARY KEY,
  run_type       TEXT,        -- 'odds_historical' | 'results_fetch' | 'build'
  sport          TEXT,
  params_json    TEXT,
  credits_used   INTEGER,
  started_at     TEXT,
  completed_at   TEXT,
  status         TEXT,        -- 'ok' | 'partial' | 'error'
  error_message  TEXT
);
```

**Schema decisions:**

1. **Long format for odds.** One row per side. Querying "spread −3.5 home at DK Q1" means one row. Joining home/away into a pair is a self-join, but the format scales to all market types cleanly.
2. **`is_close` written at ingest time.** Defined as: the snapshot with the latest `snapshot_time` ≤ `commence_time` for each (game, book, market, segment, side). Stored explicitly so closing-line queries stay fast. Recomputable from raw if logic changes.
3. **Canonical `game_id` is human-readable, deterministic from sport+date+teams.** Lets you eyeball the DB.
4. **`raw_archive_path` on every odds/scores row.** Every derived value is traceable to a specific JSON file. Schema-change recovery is `build` again.
5. **No alt-lines in v1.** Easy add later via `is_alternate INTEGER` flag on `odds_snapshots`.

---

## 5. Results Adapters & Cross-Source Identity

**Adapter interface — every sport implements one ABC:**

```python
class ResultsAdapter(ABC):
    sport: str
    segments: list[str]   # e.g. NBA: ['FULL','Q1','Q2','Q3','Q4','H1','H2','OT1','OT2',...]

    @abstractmethod
    def fetch_completed_games(self, date_from: date, date_to: date) -> list[GameResult]:
        ...

@dataclass
class GameResult:
    sport: str
    commence_time: datetime
    home_team_canonical: str
    away_team_canonical: str
    source_game_id: str
    segment_scores: dict[str, tuple[int, int]]   # {'Q1': (24,28), 'FULL': (108,102), ...}
    went_to_ot: bool
    raw_payload: dict                            # archived as-is to data/raw/results/...
```

**Per-sport library choice:**

| Sport | Library | Per-segment access |
|---|---|---|
| NBA | `nba_api` (PyPI) | `BoxScoreSummaryV2` → line score → per-quarter |
| NFL | `nfl_data_py` | `import_schedules` → `home_q1..q4` columns |
| NHL | NHL Stats API direct HTTP (no auth) | `/v1/gamecenter/{id}/landing` → `periodDescriptor` + scores |
| MLB | `MLB-StatsAPI` | linescore endpoint → per-inning |
| NCAAB | `sportsdataverse-py` or ESPN scoreboard JSON | half scores |
| NCAAF | `cfbd-api` (free API key) | `/games` endpoint → line scores |

**Identity matching (the hard part):**
The Odds API returns `event_id` + team names like `"Los Angeles Lakers"`. Each results source uses its own IDs and sometimes different team names (`"LA Lakers"`, `"Lakers"`).

```python
# odds_pipeline/identity/matcher.py
def canonical_team(sport: str, raw_name: str) -> str:
    """Look up raw_name in identity/aliases/{sport}.json; return canonical."""

def match_game(odds_event: OddsEvent, candidates: list[GameResult]) -> GameResult | None:
    """Match on: sport + commence_date (±1 day for TZ slop) + exact canonical(home) + canonical(away)."""
```

A per-sport `identity/aliases/{sport}.json` translation table is built up empirically: first pull surfaces unmatched games, we add aliases, re-run `build`. Raw archive is unchanged.

**Unmatched games are visible, not silent.** `ingest_runs.status='partial'` with the list. (Per the workspace rule: "missing data shows as missing.")

---

## 6. Odds Ingest — Bookmakers & Markets

**Endpoint:** `GET /v4/historical/sports/{sport}/events/{eventId}/odds`, with `date = commence_time - 5 minutes`. The API returns "the closest snapshot ≤ provided date", giving us the close.

**Markets per sport (`config.SPORT_MARKETS`):**

| Sport | Markets (count) |
|---|---|
| NBA | `h2h`, `spreads`, `totals`, `spreads_q1`, `totals_q1`, `spreads_h1`, `totals_h1` (7) |
| NFL | same as NBA (7) |
| NHL | `h2h`, `spreads`, `totals`, `spreads_p1`, `totals_p1` (5, no halves) |
| MLB | `h2h`, `spreads`, `totals`, `spreads_1st_5_innings`, `totals_1st_5_innings` (5) |
| NCAAB | `h2h`, `spreads`, `totals`, `spreads_h1`, `totals_h1` (5, no quarters) |
| NCAAF | same as NBA (7) |

(Note: exact key names for NHL `spreads_p1`/`totals_p1` and MLB first-5-innings markets will be verified empirically on first pull via `GET /v4/sports/{sport}/events/{eventId}/markets`. If the actual key differs, `config.SPORT_MARKETS` is the one place to update.)

**Regions:** `us` (DraftKings, FanDuel, BetMGM, others) + `eu` (Pinnacle). Two regions, ~14 credits per NBA/NFL game; ~10 credits per NHL/NCAAB/MLB game.

**Pinnacle segment-market caveat:** Pinnacle is historically light on derivatives. The first ~10 games of the sample will reveal whether Pinnacle returns any segment markets. If not, subsequent pulls drop to `us`-only region for half the cost. This is a known unknown, not a blocker.

---

## 7. CLI & Execution Flow

**Single entry point, five verbs:**

```bash
python -m odds_pipeline init
# Creates SQLite from schema.sql, seeds bookmakers + segment_types tables, verifies env. Idempotent.

python -m odds_pipeline pull-odds --sport NBA,NFL,NHL,NCAAF --from 2025-01-01 --to 2025-01-31 --limit 10
# 1. /v4/historical/sports/{sport}/events at midnight per day → event list
# 2. For each event (up to --limit per sport), /v4/historical/sports/{sport}/events/{id}/odds at commence_time - 5min
# 3. Archive raw response to data/raw/odds/{sport}/{date}/{event_id}__{snapshot_time}.json
# 4. ingest_runs row with credits_used from x-requests-used header
# Resumable: if archive file already exists, skip.

python -m odds_pipeline pull-results --sport NBA,NFL,NHL,NCAAF --from 2025-01-01 --to 2025-01-31
# Each sport's adapter fetches per-segment scores, archives raw, writes ingest_runs row.
# Free (no API credits — uses official sport feeds).

python -m odds_pipeline build
# Reads data/raw/, normalizes via identity/, populates games / odds_snapshots / scores.
# Idempotent and re-runnable: drops & rebuilds derived tables from raw.
# Logs unmatched games to ingest_runs.partial.

python -m odds_pipeline status
# Prints: credits remaining (from API), games in DB by sport, last ingest_run per sport,
# unmatched-games count, gaps ("NCAAB has 0 games for 2025-01-15 — 2025-01-20").
```

**Sample run execution:**

```
1. init                                                                (one time)
2. pull-odds --sport NBA,NFL,NHL,NCAAF --from 2025-01-01 --to 2025-01-31 --limit 10
                                                                       (~640 credits optimistic, ~6,400 if 10× rate, ~5 min)
3. pull-results --sport NBA,NFL,NHL,NCAAF --from 2025-01-01 --to 2025-01-31
                                                                       (free, ~2 min parallel)
4. build                                                               (~30 sec)
5. Inspect: open data/odds_pipeline.db in any SQLite viewer
```

**Failure handling:**

| Failure | Behavior |
|---|---|
| API rate-limited | Exponential backoff; if quota hit, halt cleanly with credits-used logged |
| One game's odds fetch fails | That `ingest_runs` row marked partial; pull continues |
| Team-name mismatch in `build` | Game lands in `games` but no `scores` row; logged with unmatched names |
| Bookmaker absent for a market | No rows for that book/market combo. Not an error. |
| Pinnacle returns no segment markets | Visible after first 10 games; re-run with `--regions us` to save credits |

---

## 8. Testing

**Per workspace rule "write tests alongside code":**

- **Per-adapter tests** using captured fixture JSON (no live API calls): one fixture file per sport, asserts `GameResult` shape.
- **Identity matcher tests** per sport: known-good (raw → canonical) team-name pairs.
- **`derive.py` golden-file test:** fixture raw archive → expected SQLite rows.
- **Integration test:** stub API responses through the full pipeline → assert query results.
- **No live API calls in CI.** All tests run against fixtures committed to `tests/fixtures/`.

---

## 9. Open Questions (to resolve during implementation)

1. **Per-event historical credit cost** — docs ambiguous (likely 1/market/region, but bulk endpoint is 10×). Log `x-requests-used` from the first response header to confirm before scaling the pull.
2. **Pinnacle segment-market coverage** — first ~10 games of the sample reveals this.
3. **NHL/MLB segment market key names** — `spreads_p1`/`totals_p1` and `spreads_1st_5_innings`/`totals_1st_5_innings` are educated guesses; verify via `/v4/sports/{sport}/events/{eventId}/markets` on first pull.
4. **NCAAB results source choice** — `sportsdataverse-py` vs raw ESPN scoreboard JSON. Pick during implementation based on which gives cleaner per-half scores.

---

## 10. v2 Hooks (deferred, but designed for)

- `is_alternate INTEGER` column on `odds_snapshots` for alt-line ingestion
- Forward-collection cron via Windows Task Scheduler that calls `pull-odds` (live `/odds` endpoint) on a schedule
- Multi-snapshot ingestion (opening + 24h + 1h + close) by changing the snapshot query loop — schema already supports it
- Pinnacle-equivalent sharp source if/when one is available — drop in as another `odds_source/` adapter

---

## 11. Out of Scope

- Modeling, EV calculation, backtesting
- Web UI (this is a CLI/library)
- Player props (different markets, different ingest cadence — separate project later)
- Live in-play odds
- Sports beyond the six listed
