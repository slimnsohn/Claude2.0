# Odds Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `apps/odds-pipeline`, a multi-sport (NBA/NFL/NHL/MLB/NCAAB/NCAAF) data layer that pulls closing odds from The Odds API and per-segment scores from sport-specific official feeds, archives every raw response, and derives a queryable SQLite database.

**Architecture:** Hybrid storage (raw JSON archive + derived SQLite). Strict module isolation: odds source and results sources both write to archive only; `store/derive.py` is the only writer to SQLite. Per-sport `ResultsAdapter` implementations normalize varying segment shapes (quarters/halves/periods/innings) at the adapter boundary.

**Tech Stack:** Python 3.11+, SQLite, `requests` (for direct HTTP), `nba_api`, `nfl_data_py`, `MLB-StatsAPI`, `cfbd-api`, `pytest`.

**Reference spec:** `docs/superpowers/specs/2026-05-24-odds-pipeline-design.md`

---

## Task 1: Project Scaffold

**Files:**
- Create: `apps/odds-pipeline/CLAUDE.md`
- Create: `apps/odds-pipeline/TODO.md`
- Create: `apps/odds-pipeline/start.bat`
- Create: `apps/odds-pipeline/pyproject.toml`
- Create: `apps/odds-pipeline/.gitignore`
- Create: `apps/odds-pipeline/odds_pipeline/__init__.py`
- Create: `apps/odds-pipeline/odds_pipeline/__main__.py`
- Create: `apps/odds-pipeline/odds_pipeline/config.py`
- Create: `apps/odds-pipeline/tests/__init__.py`
- Create: `apps/odds-pipeline/tests/test_config.py`

- [ ] **Step 1: Write the failing test**

`apps/odds-pipeline/tests/test_config.py`:
```python
import os
import pytest
from odds_pipeline import config


def test_sport_markets_covers_all_six_sports():
    expected = {"NBA", "NFL", "NHL", "MLB", "NCAAB", "NCAAF"}
    assert set(config.SPORT_MARKETS.keys()) == expected


def test_nba_markets_include_quarters_and_halves():
    nba = config.SPORT_MARKETS["NBA"]
    assert "h2h" in nba
    assert "spreads" in nba
    assert "totals" in nba
    assert "spreads_q1" in nba
    assert "totals_q1" in nba
    assert "spreads_h1" in nba
    assert "totals_h1" in nba


def test_nhl_uses_period_markets_not_quarters():
    nhl = config.SPORT_MARKETS["NHL"]
    assert "spreads_q1" not in nhl
    # Exact key name verified empirically on first pull; placeholder accepted here
    assert any("p1" in m or "period" in m for m in nhl)


def test_ncaab_has_no_quarter_markets():
    ncaab = config.SPORT_MARKETS["NCAAB"]
    assert "spreads_q1" not in ncaab
    assert "spreads_h1" in ncaab


def test_api_key_loaded_from_env(monkeypatch):
    monkeypatch.setenv("THE_ODDS_API_KEY", "test-key-123")
    # Force reimport so config re-reads env
    import importlib
    importlib.reload(config)
    assert config.THE_ODDS_API_KEY == "test-key-123"
```

- [ ] **Step 2: Run test to verify it fails**

```
cd apps/odds-pipeline
pytest tests/test_config.py -v
```
Expected: `ModuleNotFoundError: No module named 'odds_pipeline'`

- [ ] **Step 3: Write pyproject.toml**

`apps/odds-pipeline/pyproject.toml`:
```toml
[project]
name = "odds-pipeline"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "requests>=2.31",
  "nba_api>=1.4",
  "nfl_data_py>=0.3",
  "MLB-StatsAPI>=1.7",
  "cfbd>=4.6",
  "python-dateutil>=2.9",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-cov>=5.0"]

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
```

- [ ] **Step 4: Write config.py**

`apps/odds-pipeline/odds_pipeline/config.py`:
```python
"""Static config: env keys, sport->market map, segment shape per sport."""
import os

THE_ODDS_API_KEY = os.environ.get("THE_ODDS_API_KEY", "")

# Markets to pull per sport. Names assumed; verify empirically against
# GET /v4/sports/{sport}/events/{eventId}/markets on first pull.
SPORT_MARKETS = {
    "NBA":   ["h2h", "spreads", "totals", "spreads_q1", "totals_q1", "spreads_h1", "totals_h1"],
    "NFL":   ["h2h", "spreads", "totals", "spreads_q1", "totals_q1", "spreads_h1", "totals_h1"],
    "NCAAF": ["h2h", "spreads", "totals", "spreads_q1", "totals_q1", "spreads_h1", "totals_h1"],
    "NHL":   ["h2h", "spreads", "totals", "spreads_p1", "totals_p1"],
    "MLB":   ["h2h", "spreads", "totals", "spreads_1st_5_innings", "totals_1st_5_innings"],
    "NCAAB": ["h2h", "spreads", "totals", "spreads_h1", "totals_h1"],
}

# Odds API sport keys
ODDS_API_SPORT_KEYS = {
    "NBA":   "basketball_nba",
    "NFL":   "americanfootball_nfl",
    "NCAAF": "americanfootball_ncaaf",
    "NHL":   "icehockey_nhl",
    "MLB":   "baseball_mlb",
    "NCAAB": "basketball_ncaab",
}

REGIONS = ["us", "eu"]

DATA_DIR = "data"
RAW_ODDS_DIR = f"{DATA_DIR}/raw/odds"
RAW_RESULTS_DIR = f"{DATA_DIR}/raw/results"
DB_PATH = f"{DATA_DIR}/odds_pipeline.db"
```

- [ ] **Step 5: Run test to verify it passes**

```
pytest tests/test_config.py -v
```
Expected: 5 passing.

- [ ] **Step 6: Write CLAUDE.md, TODO.md, start.bat, __init__.py, __main__.py, .gitignore**

`apps/odds-pipeline/CLAUDE.md`:
```markdown
# Odds Pipeline

## Overview
Multi-sport data layer: pulls closing odds from The Odds API + per-segment scores from official sport feeds. Hybrid storage (raw JSON archive + derived SQLite). Six sports: NBA, NFL, NHL, MLB, NCAAB, NCAAF.

## Tech Stack
Python 3.11+, SQLite, requests, sport-specific libraries (nba_api, nfl_data_py, MLB-StatsAPI, cfbd).

## Quick Start
```bash
start.bat
```

## Project Structure
- `odds_pipeline/odds_source/` — The Odds API client + ingest
- `odds_pipeline/results_sources/` — One adapter per sport
- `odds_pipeline/store/` — SQLite schema + derive (raw -> tables)
- `odds_pipeline/identity/` — Cross-source game-ID matching, team aliases
- `data/raw/` — Immutable JSON archive
- `data/odds_pipeline.db` — Derived working database

## Environment Variables
- `THE_ODDS_API_KEY` — required for odds pulls
- `CFBD_API_KEY` — required for NCAAF results
```

`apps/odds-pipeline/TODO.md`:
```markdown
# TODO — odds-pipeline

## Now
- [ ] Run sample pull: NBA+NFL+NHL+NCAAF, January 2025, --limit 10

## Next
-

## Backlog
- Add `is_alternate` column for alt-line markets
- Forward-collection cron via Windows Task Scheduler
- Multi-snapshot ingestion (opening/24h/1h/close)

## Done
-
```

`apps/odds-pipeline/start.bat`:
```batch
@echo off
cd /d "%~dp0"
python -m odds_pipeline %*
```

`apps/odds-pipeline/odds_pipeline/__init__.py`:
```python
"""Multi-sport odds + results data pipeline."""
__version__ = "0.1.0"
```

`apps/odds-pipeline/odds_pipeline/__main__.py`:
```python
from odds_pipeline.cli import main

if __name__ == "__main__":
    main()
```

`apps/odds-pipeline/.gitignore`:
```
__pycache__/
*.pyc
.pytest_cache/
data/
*.db
.coverage
htmlcov/
```

- [ ] **Step 7: Commit**

```bash
git add apps/odds-pipeline/
git commit -m "feat(odds-pipeline): scaffold project with config and sport-market map"
```

---

## Task 2: Database Schema + Migrate

**Files:**
- Create: `apps/odds-pipeline/odds_pipeline/store/__init__.py`
- Create: `apps/odds-pipeline/odds_pipeline/store/schema.sql`
- Create: `apps/odds-pipeline/odds_pipeline/store/migrate.py`
- Create: `apps/odds-pipeline/tests/test_migrate.py`

- [ ] **Step 1: Write the failing test**

`apps/odds-pipeline/tests/test_migrate.py`:
```python
import sqlite3
from pathlib import Path
import pytest
from odds_pipeline.store import migrate


def test_init_db_creates_all_tables(tmp_path):
    db_path = tmp_path / "test.db"
    migrate.init_db(str(db_path))
    conn = sqlite3.connect(db_path)
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert tables == {
        "segment_types", "bookmakers", "games",
        "odds_snapshots", "scores", "ingest_runs",
    }


def test_init_db_is_idempotent(tmp_path):
    db_path = tmp_path / "test.db"
    migrate.init_db(str(db_path))
    migrate.init_db(str(db_path))  # second call must not error


def test_games_table_has_unique_event_id(tmp_path):
    db_path = tmp_path / "test.db"
    migrate.init_db(str(db_path))
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO games (game_id, sport, commence_time, home_team, away_team, odds_api_event_id) "
        "VALUES ('A', 'NBA', '2025-01-01T00:00Z', 'X', 'Y', 'evt-1')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO games (game_id, sport, commence_time, home_team, away_team, odds_api_event_id) "
            "VALUES ('B', 'NBA', '2025-01-02T00:00Z', 'X', 'Y', 'evt-1')"
        )


def test_odds_snapshots_foreign_keys_enforced(tmp_path):
    db_path = tmp_path / "test.db"
    migrate.init_db(str(db_path))
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO odds_snapshots (game_id, bookmaker_key, segment_key, market_type, side, price_american, snapshot_time, raw_archive_path) "
            "VALUES ('nonexistent', 'pinnacle', 'FULL', 'h2h', 'home', -150, '2025-01-01T00:00Z', 'x.json')"
        )
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_migrate.py -v
```
Expected: `ModuleNotFoundError: No module named 'odds_pipeline.store'`

- [ ] **Step 3: Write schema.sql**

`apps/odds-pipeline/odds_pipeline/store/schema.sql`:
```sql
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS segment_types (
  sport         TEXT,
  segment_key   TEXT,
  kind          TEXT,
  order_idx     INTEGER,
  PRIMARY KEY (sport, segment_key)
);

CREATE TABLE IF NOT EXISTS bookmakers (
  key      TEXT PRIMARY KEY,
  title    TEXT,
  region   TEXT,
  sharp    INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS games (
  game_id                  TEXT PRIMARY KEY,
  sport                    TEXT NOT NULL,
  commence_time            TEXT NOT NULL,
  home_team                TEXT NOT NULL,
  away_team                TEXT NOT NULL,
  season                   INTEGER,
  season_type              TEXT,
  odds_api_event_id        TEXT UNIQUE,
  results_source_game_id   TEXT,
  created_at               TEXT,
  updated_at               TEXT
);
CREATE INDEX IF NOT EXISTS idx_games_sport_date ON games(sport, commence_time);

CREATE TABLE IF NOT EXISTS odds_snapshots (
  snapshot_id      INTEGER PRIMARY KEY,
  game_id          TEXT NOT NULL REFERENCES games(game_id),
  bookmaker_key    TEXT NOT NULL REFERENCES bookmakers(key),
  segment_key      TEXT NOT NULL,
  market_type      TEXT NOT NULL,
  side             TEXT NOT NULL,
  line             REAL,
  price_american   INTEGER NOT NULL,
  price_decimal    REAL,
  snapshot_time    TEXT NOT NULL,
  is_close         INTEGER NOT NULL DEFAULT 0,
  raw_archive_path TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_odds_game ON odds_snapshots(game_id);
CREATE INDEX IF NOT EXISTS idx_odds_close ON odds_snapshots(game_id, is_close) WHERE is_close = 1;

CREATE TABLE IF NOT EXISTS scores (
  game_id          TEXT NOT NULL REFERENCES games(game_id),
  segment_key      TEXT NOT NULL,
  home_score       INTEGER NOT NULL,
  away_score       INTEGER NOT NULL,
  raw_archive_path TEXT NOT NULL,
  PRIMARY KEY (game_id, segment_key)
);

CREATE TABLE IF NOT EXISTS ingest_runs (
  run_id         INTEGER PRIMARY KEY,
  run_type       TEXT,
  sport          TEXT,
  params_json    TEXT,
  credits_used   INTEGER,
  started_at     TEXT,
  completed_at   TEXT,
  status         TEXT,
  error_message  TEXT
);
```

- [ ] **Step 4: Write migrate.py**

`apps/odds-pipeline/odds_pipeline/store/migrate.py`:
```python
"""Database schema migration."""
import sqlite3
from pathlib import Path


SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def init_db(db_path: str) -> None:
    """Create database from schema.sql. Idempotent."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_PATH.read_text())
    conn.commit()
    conn.close()
```

`apps/odds-pipeline/odds_pipeline/store/__init__.py`:
```python
"""SQLite storage layer."""
```

- [ ] **Step 5: Run test to verify it passes**

```
pytest tests/test_migrate.py -v
```
Expected: 4 passing.

- [ ] **Step 6: Commit**

```bash
git add apps/odds-pipeline/odds_pipeline/store/ apps/odds-pipeline/tests/test_migrate.py
git commit -m "feat(odds-pipeline): add SQLite schema and migration"
```

---

## Task 3: Reference Data Seeding

**Files:**
- Create: `apps/odds-pipeline/odds_pipeline/store/seed.py`
- Create: `apps/odds-pipeline/tests/test_seed.py`

- [ ] **Step 1: Write the failing test**

`apps/odds-pipeline/tests/test_seed.py`:
```python
import sqlite3
from odds_pipeline.store import migrate, seed


def test_seed_bookmakers_inserts_known_books(tmp_path):
    db_path = tmp_path / "test.db"
    migrate.init_db(str(db_path))
    seed.seed_bookmakers(str(db_path))
    conn = sqlite3.connect(db_path)
    keys = {row[0] for row in conn.execute("SELECT key FROM bookmakers")}
    assert {"pinnacle", "draftkings", "fanduel", "betmgm"} <= keys


def test_pinnacle_is_marked_sharp(tmp_path):
    db_path = tmp_path / "test.db"
    migrate.init_db(str(db_path))
    seed.seed_bookmakers(str(db_path))
    conn = sqlite3.connect(db_path)
    sharp = conn.execute(
        "SELECT sharp FROM bookmakers WHERE key='pinnacle'"
    ).fetchone()[0]
    assert sharp == 1


def test_seed_segment_types_covers_all_sports(tmp_path):
    db_path = tmp_path / "test.db"
    migrate.init_db(str(db_path))
    seed.seed_segment_types(str(db_path))
    conn = sqlite3.connect(db_path)
    sports = {row[0] for row in conn.execute("SELECT DISTINCT sport FROM segment_types")}
    assert sports == {"NBA", "NFL", "NHL", "MLB", "NCAAB", "NCAAF"}


def test_nba_segments_include_quarters_halves_overtime(tmp_path):
    db_path = tmp_path / "test.db"
    migrate.init_db(str(db_path))
    seed.seed_segment_types(str(db_path))
    conn = sqlite3.connect(db_path)
    keys = {row[0] for row in conn.execute(
        "SELECT segment_key FROM segment_types WHERE sport='NBA'"
    )}
    assert {"FULL", "Q1", "Q2", "Q3", "Q4", "H1", "H2", "OT1"} <= keys


def test_nhl_uses_periods_and_shootout(tmp_path):
    db_path = tmp_path / "test.db"
    migrate.init_db(str(db_path))
    seed.seed_segment_types(str(db_path))
    conn = sqlite3.connect(db_path)
    keys = {row[0] for row in conn.execute(
        "SELECT segment_key FROM segment_types WHERE sport='NHL'"
    )}
    assert {"FULL", "P1", "P2", "P3", "OT1", "SO"} <= keys


def test_seed_is_idempotent(tmp_path):
    db_path = tmp_path / "test.db"
    migrate.init_db(str(db_path))
    seed.seed_bookmakers(str(db_path))
    seed.seed_bookmakers(str(db_path))  # second call must not duplicate
    conn = sqlite3.connect(db_path)
    pinnacle_count = conn.execute(
        "SELECT COUNT(*) FROM bookmakers WHERE key='pinnacle'"
    ).fetchone()[0]
    assert pinnacle_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_seed.py -v
```
Expected: `ImportError: cannot import name 'seed'`

- [ ] **Step 3: Write seed.py**

`apps/odds-pipeline/odds_pipeline/store/seed.py`:
```python
"""Seed reference tables: bookmakers and segment_types."""
import sqlite3

BOOKMAKERS = [
    # key, title, region, sharp
    ("pinnacle",   "Pinnacle",   "eu", 1),
    ("draftkings", "DraftKings", "us", 0),
    ("fanduel",    "FanDuel",    "us", 0),
    ("betmgm",     "BetMGM",     "us", 0),
    ("caesars",    "Caesars",    "us", 0),
    ("betrivers",  "BetRivers",  "us", 0),
    ("pointsbetus","PointsBet",  "us", 0),
    ("williamhill_us", "William Hill US", "us", 0),
]

# Segment types per sport. (sport, segment_key, kind, order_idx)
SEGMENT_TYPES = [
    # NBA: 4 quarters, 2 halves, FULL, up to 4 OTs
    ("NBA", "FULL", "full",    0),
    ("NBA", "Q1",   "quarter", 1),
    ("NBA", "Q2",   "quarter", 2),
    ("NBA", "Q3",   "quarter", 3),
    ("NBA", "Q4",   "quarter", 4),
    ("NBA", "H1",   "half",    5),
    ("NBA", "H2",   "half",    6),
    ("NBA", "OT1",  "overtime", 7),
    ("NBA", "OT2",  "overtime", 8),
    ("NBA", "OT3",  "overtime", 9),
    ("NBA", "OT4",  "overtime", 10),
    # NFL: same shape as NBA, single OT
    ("NFL", "FULL", "full",    0),
    ("NFL", "Q1",   "quarter", 1),
    ("NFL", "Q2",   "quarter", 2),
    ("NFL", "Q3",   "quarter", 3),
    ("NFL", "Q4",   "quarter", 4),
    ("NFL", "H1",   "half",    5),
    ("NFL", "H2",   "half",    6),
    ("NFL", "OT1",  "overtime", 7),
    # NCAAF: like NFL but multiple OTs possible
    ("NCAAF", "FULL", "full",    0),
    ("NCAAF", "Q1",   "quarter", 1),
    ("NCAAF", "Q2",   "quarter", 2),
    ("NCAAF", "Q3",   "quarter", 3),
    ("NCAAF", "Q4",   "quarter", 4),
    ("NCAAF", "H1",   "half",    5),
    ("NCAAF", "H2",   "half",    6),
    ("NCAAF", "OT1",  "overtime", 7),
    ("NCAAF", "OT2",  "overtime", 8),
    ("NCAAF", "OT3",  "overtime", 9),
    # NHL: 3 periods, OT, shootout
    ("NHL", "FULL", "full",     0),
    ("NHL", "P1",   "period",   1),
    ("NHL", "P2",   "period",   2),
    ("NHL", "P3",   "period",   3),
    ("NHL", "OT1",  "overtime", 4),
    ("NHL", "SO",   "shootout", 5),
    # NCAAB: 2 halves, multiple OTs
    ("NCAAB", "FULL", "full",     0),
    ("NCAAB", "H1",   "half",     1),
    ("NCAAB", "H2",   "half",     2),
    ("NCAAB", "OT1",  "overtime", 3),
    ("NCAAB", "OT2",  "overtime", 4),
    # MLB: 9 innings, F5 inning_range
    ("MLB", "FULL",  "full",          0),
    ("MLB", "INN1",  "inning",        1),
    ("MLB", "INN2",  "inning",        2),
    ("MLB", "INN3",  "inning",        3),
    ("MLB", "INN4",  "inning",        4),
    ("MLB", "INN5",  "inning",        5),
    ("MLB", "INN6",  "inning",        6),
    ("MLB", "INN7",  "inning",        7),
    ("MLB", "INN8",  "inning",        8),
    ("MLB", "INN9",  "inning",        9),
    ("MLB", "F5",    "inning_range",  10),
]


def seed_bookmakers(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.executemany(
        "INSERT OR IGNORE INTO bookmakers (key, title, region, sharp) VALUES (?, ?, ?, ?)",
        BOOKMAKERS,
    )
    conn.commit()
    conn.close()


def seed_segment_types(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.executemany(
        "INSERT OR IGNORE INTO segment_types (sport, segment_key, kind, order_idx) VALUES (?, ?, ?, ?)",
        SEGMENT_TYPES,
    )
    conn.commit()
    conn.close()


def seed_all(db_path: str) -> None:
    seed_bookmakers(db_path)
    seed_segment_types(db_path)
```

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/test_seed.py -v
```
Expected: 6 passing.

- [ ] **Step 5: Commit**

```bash
git add apps/odds-pipeline/odds_pipeline/store/seed.py apps/odds-pipeline/tests/test_seed.py
git commit -m "feat(odds-pipeline): seed bookmakers and segment_types reference tables"
```

---

## Task 4: Identity Layer (canonical names + matcher)

**Files:**
- Create: `apps/odds-pipeline/odds_pipeline/identity/__init__.py`
- Create: `apps/odds-pipeline/odds_pipeline/identity/matcher.py`
- Create: `apps/odds-pipeline/odds_pipeline/identity/aliases/NBA.json`
- Create: `apps/odds-pipeline/odds_pipeline/identity/aliases/NFL.json`
- Create: `apps/odds-pipeline/odds_pipeline/identity/aliases/NHL.json`
- Create: `apps/odds-pipeline/odds_pipeline/identity/aliases/MLB.json`
- Create: `apps/odds-pipeline/odds_pipeline/identity/aliases/NCAAB.json`
- Create: `apps/odds-pipeline/odds_pipeline/identity/aliases/NCAAF.json`
- Create: `apps/odds-pipeline/tests/test_identity.py`

- [ ] **Step 1: Write the failing test**

`apps/odds-pipeline/tests/test_identity.py`:
```python
from datetime import datetime, timezone
from odds_pipeline.identity import matcher


def test_canonical_nba_lakers_variants():
    assert matcher.canonical_team("NBA", "Los Angeles Lakers") == "LAL"
    assert matcher.canonical_team("NBA", "LA Lakers") == "LAL"
    assert matcher.canonical_team("NBA", "Lakers") == "LAL"


def test_canonical_unknown_returns_input_uppercased():
    # Unknown names pass through (with a sentinel) so they show up in
    # the unmatched-games log rather than silently failing.
    result = matcher.canonical_team("NBA", "Some Brand New Team")
    assert result == "SOME BRAND NEW TEAM" or result is None


def test_build_game_id_format():
    commence = datetime(2025, 1, 15, 19, 30, tzinfo=timezone.utc)
    game_id = matcher.build_game_id("NBA", commence, home="LAL", away="BOS")
    assert game_id == "NBA:20250115:BOS@LAL"


def test_match_game_exact_match():
    from odds_pipeline.identity.matcher import OddsEvent, ResultCandidate

    odds = OddsEvent(
        sport="NBA",
        commence_time=datetime(2025, 1, 15, 19, 30, tzinfo=timezone.utc),
        home_team_raw="Los Angeles Lakers",
        away_team_raw="Boston Celtics",
        event_id="evt-1",
    )
    candidates = [
        ResultCandidate(
            sport="NBA",
            commence_time=datetime(2025, 1, 15, 0, 0, tzinfo=timezone.utc),
            home_team_canonical="LAL",
            away_team_canonical="BOS",
            source_game_id="0022400500",
        ),
    ]
    match = matcher.match_game(odds, candidates)
    assert match is not None
    assert match.source_game_id == "0022400500"


def test_match_game_no_match_returns_none():
    from odds_pipeline.identity.matcher import OddsEvent, ResultCandidate

    odds = OddsEvent(
        sport="NBA",
        commence_time=datetime(2025, 1, 15, 19, 30, tzinfo=timezone.utc),
        home_team_raw="Los Angeles Lakers",
        away_team_raw="Boston Celtics",
        event_id="evt-1",
    )
    candidates = [
        ResultCandidate(
            sport="NBA",
            commence_time=datetime(2025, 1, 15, 0, 0, tzinfo=timezone.utc),
            home_team_canonical="MIA",
            away_team_canonical="NYK",
            source_game_id="X",
        ),
    ]
    assert matcher.match_game(odds, candidates) is None
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_identity.py -v
```
Expected: import errors.

- [ ] **Step 3: Write NBA aliases**

`apps/odds-pipeline/odds_pipeline/identity/aliases/NBA.json`:
```json
{
  "Atlanta Hawks": "ATL",
  "Boston Celtics": "BOS",
  "Brooklyn Nets": "BKN",
  "Charlotte Hornets": "CHA",
  "Chicago Bulls": "CHI",
  "Cleveland Cavaliers": "CLE",
  "Dallas Mavericks": "DAL",
  "Denver Nuggets": "DEN",
  "Detroit Pistons": "DET",
  "Golden State Warriors": "GSW",
  "Houston Rockets": "HOU",
  "Indiana Pacers": "IND",
  "LA Clippers": "LAC",
  "Los Angeles Clippers": "LAC",
  "Los Angeles Lakers": "LAL",
  "LA Lakers": "LAL",
  "Lakers": "LAL",
  "Memphis Grizzlies": "MEM",
  "Miami Heat": "MIA",
  "Milwaukee Bucks": "MIL",
  "Minnesota Timberwolves": "MIN",
  "New Orleans Pelicans": "NOP",
  "New York Knicks": "NYK",
  "Oklahoma City Thunder": "OKC",
  "Orlando Magic": "ORL",
  "Philadelphia 76ers": "PHI",
  "Phoenix Suns": "PHX",
  "Portland Trail Blazers": "POR",
  "Sacramento Kings": "SAC",
  "San Antonio Spurs": "SAS",
  "Toronto Raptors": "TOR",
  "Utah Jazz": "UTA",
  "Washington Wizards": "WAS"
}
```

For the other five sports, create stub JSON files with `{}` — they will be filled empirically as unmatched names surface in the first sample run. This is by design (per spec section 5).

`apps/odds-pipeline/odds_pipeline/identity/aliases/NFL.json`, `NHL.json`, `MLB.json`, `NCAAB.json`, `NCAAF.json`:
```json
{}
```

- [ ] **Step 4: Write matcher.py**

`apps/odds-pipeline/odds_pipeline/identity/matcher.py`:
```python
"""Cross-source identity matching: team name canonicalization and game matching."""
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

ALIASES_DIR = Path(__file__).parent / "aliases"

_alias_cache: dict[str, dict[str, str]] = {}


def _load_aliases(sport: str) -> dict[str, str]:
    if sport not in _alias_cache:
        path = ALIASES_DIR / f"{sport}.json"
        _alias_cache[sport] = json.loads(path.read_text()) if path.exists() else {}
    return _alias_cache[sport]


def canonical_team(sport: str, raw_name: str) -> str:
    """Look up raw_name in identity/aliases/{sport}.json; return canonical or upper-cased raw."""
    aliases = _load_aliases(sport)
    if raw_name in aliases:
        return aliases[raw_name]
    return raw_name.upper()


def build_game_id(sport: str, commence_time: datetime, home: str, away: str) -> str:
    """'{sport}:{yyyymmdd}:{away}@{home}'."""
    return f"{sport}:{commence_time.strftime('%Y%m%d')}:{away}@{home}"


@dataclass
class OddsEvent:
    sport: str
    commence_time: datetime
    home_team_raw: str
    away_team_raw: str
    event_id: str


@dataclass
class ResultCandidate:
    sport: str
    commence_time: datetime
    home_team_canonical: str
    away_team_canonical: str
    source_game_id: str


def match_game(odds: OddsEvent, candidates: list[ResultCandidate]) -> ResultCandidate | None:
    """Match odds event to a results candidate. Date tolerance: ±1 day (TZ slop)."""
    odds_home = canonical_team(odds.sport, odds.home_team_raw)
    odds_away = canonical_team(odds.sport, odds.away_team_raw)
    for c in candidates:
        if c.sport != odds.sport:
            continue
        if abs((c.commence_time - odds.commence_time).total_seconds()) > 86400:
            continue
        if c.home_team_canonical == odds_home and c.away_team_canonical == odds_away:
            return c
    return None
```

`apps/odds-pipeline/odds_pipeline/identity/__init__.py`:
```python
"""Cross-source identity matching."""
```

- [ ] **Step 5: Run test to verify it passes**

```
pytest tests/test_identity.py -v
```
Expected: 5 passing.

- [ ] **Step 6: Commit**

```bash
git add apps/odds-pipeline/odds_pipeline/identity/ apps/odds-pipeline/tests/test_identity.py
git commit -m "feat(odds-pipeline): identity layer with NBA aliases and game matcher"
```

---

## Task 5: The Odds API Client

**Files:**
- Create: `apps/odds-pipeline/odds_pipeline/odds_source/__init__.py`
- Create: `apps/odds-pipeline/odds_pipeline/odds_source/client.py`
- Create: `apps/odds-pipeline/tests/test_odds_client.py`
- Create: `apps/odds-pipeline/tests/fixtures/odds_api/historical_events_nba_20250115.json`
- Create: `apps/odds-pipeline/tests/fixtures/odds_api/historical_event_odds_nba.json`

- [ ] **Step 1: Capture real fixture data**

Before writing tests, run one real call against the API to capture a realistic response shape. This is a one-time setup step, not part of the test suite. Use the free 500-credit tier or your existing key.

Run manually (one-time, save outputs as fixtures):
```bash
# Historical event list
curl "https://api.the-odds-api.com/v4/historical/sports/basketball_nba/events?apiKey=$THE_ODDS_API_KEY&date=2025-01-15T12:00:00Z" \
  > tests/fixtures/odds_api/historical_events_nba_20250115.json

# Pick one event_id from the response, then:
curl "https://api.the-odds-api.com/v4/historical/sports/basketball_nba/events/{event_id}/odds?apiKey=$THE_ODDS_API_KEY&date=2025-01-16T00:25:00Z&regions=us,eu&markets=h2h,spreads,totals,spreads_q1,totals_q1,spreads_h1,totals_h1&oddsFormat=american" \
  > tests/fixtures/odds_api/historical_event_odds_nba.json
```

Commit the fixtures.

- [ ] **Step 2: Write the failing test**

`apps/odds-pipeline/tests/test_odds_client.py`:
```python
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock
from odds_pipeline.odds_source import client

FIXTURES = Path(__file__).parent / "fixtures" / "odds_api"


def _mock_response(status, body, headers=None):
    m = MagicMock()
    m.status_code = status
    m.json.return_value = body
    m.headers = headers or {}
    m.text = json.dumps(body)
    return m


def test_get_historical_events_parses_response():
    fixture = json.loads((FIXTURES / "historical_events_nba_20250115.json").read_text())
    with patch.object(client.requests, "get", return_value=_mock_response(
        200, fixture, {"x-requests-used": "12", "x-requests-remaining": "19988"}
    )):
        c = client.TheOddsApiClient(api_key="x")
        events, usage = c.get_historical_events(
            "basketball_nba",
            datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc),
        )
    assert isinstance(events, list)
    assert usage.requests_used == 12
    assert usage.requests_remaining == 19988


def test_get_historical_event_odds_returns_payload_and_usage():
    fixture = json.loads((FIXTURES / "historical_event_odds_nba.json").read_text())
    with patch.object(client.requests, "get", return_value=_mock_response(
        200, fixture, {"x-requests-used": "26", "x-requests-remaining": "19974"}
    )):
        c = client.TheOddsApiClient(api_key="x")
        payload, usage = c.get_historical_event_odds(
            "basketball_nba",
            "evt-1",
            datetime(2025, 1, 16, 0, 25, tzinfo=timezone.utc),
            regions=["us", "eu"],
            markets=["h2h", "spreads"],
        )
    assert payload == fixture
    assert usage.requests_used == 26


def test_client_retries_on_429(monkeypatch):
    monkeypatch.setattr(client, "BACKOFF_SECONDS", [0, 0, 0])
    rate_limited = _mock_response(429, {}, {})
    success = _mock_response(200, [], {"x-requests-used": "1"})
    with patch.object(client.requests, "get", side_effect=[rate_limited, success]):
        c = client.TheOddsApiClient(api_key="x")
        events, usage = c.get_historical_events(
            "basketball_nba",
            datetime(2025, 1, 15, tzinfo=timezone.utc),
        )
    assert events == []
```

- [ ] **Step 3: Run test to verify it fails**

```
pytest tests/test_odds_client.py -v
```
Expected: import error.

- [ ] **Step 4: Write client.py**

`apps/odds-pipeline/odds_pipeline/odds_source/client.py`:
```python
"""The Odds API HTTP client with rate-limit retries and credit tracking."""
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import requests

BASE_URL = "https://api.the-odds-api.com/v4"
BACKOFF_SECONDS = [1, 4, 16]


@dataclass
class Usage:
    requests_used: int
    requests_remaining: Optional[int]
    last_cost: Optional[int]


class TheOddsApiClient:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def _get(self, path: str, params: dict) -> tuple[dict | list, Usage]:
        params = {**params, "apiKey": self.api_key}
        url = f"{BASE_URL}{path}"
        last_err = None
        for delay in BACKOFF_SECONDS + [None]:
            resp = requests.get(url, params=params, timeout=30)
            if resp.status_code == 200:
                u = Usage(
                    requests_used=int(resp.headers.get("x-requests-used", 0)),
                    requests_remaining=int(resp.headers["x-requests-remaining"])
                        if "x-requests-remaining" in resp.headers else None,
                    last_cost=int(resp.headers["x-requests-last"])
                        if "x-requests-last" in resp.headers else None,
                )
                return resp.json(), u
            if resp.status_code == 429 and delay is not None:
                time.sleep(delay)
                continue
            last_err = f"HTTP {resp.status_code}: {resp.text[:200]}"
            break
        raise RuntimeError(f"Odds API call failed: {last_err}")

    def get_historical_events(self, sport_key: str, date: datetime) -> tuple[list, Usage]:
        return self._get(
            f"/historical/sports/{sport_key}/events",
            {"date": date.strftime("%Y-%m-%dT%H:%M:%SZ")},
        )

    def get_historical_event_odds(
        self, sport_key: str, event_id: str, date: datetime,
        regions: list[str], markets: list[str],
    ) -> tuple[dict, Usage]:
        return self._get(
            f"/historical/sports/{sport_key}/events/{event_id}/odds",
            {
                "date": date.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "regions": ",".join(regions),
                "markets": ",".join(markets),
                "oddsFormat": "american",
            },
        )
```

`apps/odds-pipeline/odds_pipeline/odds_source/__init__.py`:
```python
"""The Odds API integration."""
```

- [ ] **Step 5: Run test to verify it passes**

```
pytest tests/test_odds_client.py -v
```
Expected: 3 passing.

- [ ] **Step 6: Commit**

```bash
git add apps/odds-pipeline/odds_pipeline/odds_source/ apps/odds-pipeline/tests/test_odds_client.py apps/odds-pipeline/tests/fixtures/
git commit -m "feat(odds-pipeline): The Odds API client with retry and credit tracking"
```

---

## Task 6: Archive Layer (Raw JSON Writer)

**Files:**
- Create: `apps/odds-pipeline/odds_pipeline/archive.py`
- Create: `apps/odds-pipeline/tests/test_archive.py`

- [ ] **Step 1: Write the failing test**

`apps/odds-pipeline/tests/test_archive.py`:
```python
import json
from datetime import datetime, timezone
from odds_pipeline import archive


def test_write_odds_archive_creates_deterministic_path(tmp_path):
    path = archive.write_odds(
        root=str(tmp_path),
        sport="NBA",
        event_id="evt-abc",
        snapshot_time=datetime(2025, 1, 16, 0, 25, tzinfo=timezone.utc),
        payload={"foo": "bar"},
    )
    assert path.endswith("NBA/2025-01-16/evt-abc__20250116T002500Z.json")
    assert json.loads(open(path).read()) == {"foo": "bar"}


def test_write_odds_uses_commence_date_not_today(tmp_path):
    path = archive.write_odds(
        root=str(tmp_path),
        sport="NBA",
        event_id="x",
        snapshot_time=datetime(2025, 1, 16, 0, 25, tzinfo=timezone.utc),
        payload={},
    )
    assert "2025-01-16" in path


def test_write_results_path_includes_game_id(tmp_path):
    path = archive.write_results(
        root=str(tmp_path),
        sport="NBA",
        game_id="NBA:20250115:BOS@LAL",
        payload={"score": 108},
    )
    assert path.endswith("NBA/NBA:20250115:BOS@LAL.json")


def test_exists_returns_true_after_write(tmp_path):
    archive.write_odds(
        root=str(tmp_path), sport="NBA", event_id="e",
        snapshot_time=datetime(2025, 1, 16, 0, 25, tzinfo=timezone.utc),
        payload={},
    )
    assert archive.odds_archive_exists(
        root=str(tmp_path), sport="NBA", event_id="e",
        snapshot_time=datetime(2025, 1, 16, 0, 25, tzinfo=timezone.utc),
    )
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_archive.py -v
```
Expected: `ModuleNotFoundError: No module named 'odds_pipeline.archive'`

- [ ] **Step 3: Write archive.py**

`apps/odds-pipeline/odds_pipeline/archive.py`:
```python
"""Immutable raw JSON archive."""
import json
from datetime import datetime
from pathlib import Path


def _odds_path(root: str, sport: str, event_id: str, snapshot_time: datetime) -> Path:
    date_dir = snapshot_time.strftime("%Y-%m-%d")
    fname = f"{event_id}__{snapshot_time.strftime('%Y%m%dT%H%M%SZ')}.json"
    return Path(root) / sport / date_dir / fname


def write_odds(*, root: str, sport: str, event_id: str,
               snapshot_time: datetime, payload: dict | list) -> str:
    p = _odds_path(root, sport, event_id, snapshot_time)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, default=str))
    return str(p)


def odds_archive_exists(*, root: str, sport: str, event_id: str,
                        snapshot_time: datetime) -> bool:
    return _odds_path(root, sport, event_id, snapshot_time).exists()


def write_results(*, root: str, sport: str, game_id: str, payload: dict) -> str:
    p = Path(root) / sport / f"{game_id}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, default=str))
    return str(p)


def results_archive_exists(*, root: str, sport: str, game_id: str) -> bool:
    return (Path(root) / sport / f"{game_id}.json").exists()
```

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/test_archive.py -v
```
Expected: 4 passing.

- [ ] **Step 5: Commit**

```bash
git add apps/odds-pipeline/odds_pipeline/archive.py apps/odds-pipeline/tests/test_archive.py
git commit -m "feat(odds-pipeline): raw JSON archive with deterministic paths"
```

---

## Task 7: Odds Ingest Service + pull-odds Command

**Files:**
- Create: `apps/odds-pipeline/odds_pipeline/odds_source/ingest.py`
- Create: `apps/odds-pipeline/odds_pipeline/cli.py`
- Create: `apps/odds-pipeline/tests/test_odds_ingest.py`

- [ ] **Step 1: Write the failing test**

`apps/odds-pipeline/tests/test_odds_ingest.py`:
```python
import json
from datetime import datetime, date, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
from odds_pipeline.odds_source import ingest
from odds_pipeline.odds_source.client import Usage

FIXTURES = Path(__file__).parent / "fixtures" / "odds_api"


def test_pull_odds_for_sport_writes_one_archive_per_event(tmp_path):
    events_payload = [
        {"id": "evt-1", "commence_time": "2025-01-16T01:00:00Z",
         "home_team": "Boston Celtics", "away_team": "Los Angeles Lakers"},
        {"id": "evt-2", "commence_time": "2025-01-16T03:30:00Z",
         "home_team": "Miami Heat", "away_team": "New York Knicks"},
    ]
    odds_payload = json.loads((FIXTURES / "historical_event_odds_nba.json").read_text())

    mock_client = MagicMock()
    mock_client.get_historical_events.return_value = (events_payload, Usage(0, 19999, 1))
    mock_client.get_historical_event_odds.return_value = (odds_payload, Usage(0, 19998, 14))

    result = ingest.pull_odds_for_sport(
        client=mock_client,
        sport="NBA",
        date_from=date(2025, 1, 16),
        date_to=date(2025, 1, 16),
        regions=["us", "eu"],
        archive_root=str(tmp_path),
        limit=None,
    )

    assert result.events_processed == 2
    assert result.events_archived == 2
    assert (tmp_path / "NBA" / "2025-01-16").exists()
    archived_files = list((tmp_path / "NBA" / "2025-01-16").glob("*.json"))
    assert len(archived_files) == 2


def test_pull_odds_respects_limit(tmp_path):
    events_payload = [
        {"id": f"evt-{i}", "commence_time": "2025-01-16T01:00:00Z",
         "home_team": "A", "away_team": "B"} for i in range(20)
    ]
    mock_client = MagicMock()
    mock_client.get_historical_events.return_value = (events_payload, Usage(0, 20000, 1))
    mock_client.get_historical_event_odds.return_value = ({}, Usage(0, 19999, 14))

    result = ingest.pull_odds_for_sport(
        client=mock_client, sport="NBA",
        date_from=date(2025, 1, 16), date_to=date(2025, 1, 16),
        regions=["us", "eu"], archive_root=str(tmp_path), limit=5,
    )
    assert result.events_archived == 5


def test_pull_odds_skips_already_archived(tmp_path):
    events_payload = [
        {"id": "evt-1", "commence_time": "2025-01-16T01:00:00Z",
         "home_team": "A", "away_team": "B"},
    ]
    # Pre-create the archive file at the snapshot path the ingest would compute.
    snapshot_dir = tmp_path / "NBA" / "2025-01-16"
    snapshot_dir.mkdir(parents=True)
    # Snapshot time = commence_time - 5min = 2025-01-16T00:55:00Z
    (snapshot_dir / "evt-1__20250116T005500Z.json").write_text("{}")

    mock_client = MagicMock()
    mock_client.get_historical_events.return_value = (events_payload, Usage(0, 20000, 1))
    mock_client.get_historical_event_odds.return_value = ({}, Usage(0, 19999, 14))

    result = ingest.pull_odds_for_sport(
        client=mock_client, sport="NBA",
        date_from=date(2025, 1, 16), date_to=date(2025, 1, 16),
        regions=["us", "eu"], archive_root=str(tmp_path), limit=None,
    )
    # Did NOT call get_historical_event_odds, since archive existed
    assert mock_client.get_historical_event_odds.call_count == 0
    assert result.events_skipped == 1
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_odds_ingest.py -v
```
Expected: import error.

- [ ] **Step 3: Write ingest.py**

`apps/odds-pipeline/odds_pipeline/odds_source/ingest.py`:
```python
"""Historical odds ingest: iterate dates, list events, pull odds, archive."""
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from dateutil import parser as dtparser

from odds_pipeline import archive, config
from odds_pipeline.odds_source.client import TheOddsApiClient


@dataclass
class PullResult:
    events_processed: int = 0
    events_archived: int = 0
    events_skipped: int = 0
    events_failed: int = 0
    credits_used: int = 0
    errors: list[str] = field(default_factory=list)


def pull_odds_for_sport(
    *,
    client: TheOddsApiClient,
    sport: str,
    date_from: date,
    date_to: date,
    regions: list[str],
    archive_root: str,
    limit: int | None,
) -> PullResult:
    """Iterate days, list events per day, pull odds for each event at commence_time - 5min."""
    sport_key = config.ODDS_API_SPORT_KEYS[sport]
    markets = config.SPORT_MARKETS[sport]
    result = PullResult()

    cur = date_from
    archived_in_sport = 0
    while cur <= date_to:
        list_date = datetime(cur.year, cur.month, cur.day, 12, 0, tzinfo=timezone.utc)
        try:
            events, list_usage = client.get_historical_events(sport_key, list_date)
        except Exception as e:
            result.errors.append(f"events {sport} {cur}: {e}")
            result.events_failed += 1
            cur += timedelta(days=1)
            continue
        result.credits_used += list_usage.last_cost or 0

        for evt in events:
            if limit is not None and archived_in_sport >= limit:
                break
            result.events_processed += 1
            commence = dtparser.isoparse(evt["commence_time"])
            snapshot_time = commence - timedelta(minutes=5)

            if archive.odds_archive_exists(
                root=archive_root, sport=sport,
                event_id=evt["id"], snapshot_time=snapshot_time,
            ):
                result.events_skipped += 1
                continue

            try:
                payload, usage = client.get_historical_event_odds(
                    sport_key=sport_key, event_id=evt["id"],
                    date=snapshot_time, regions=regions, markets=markets,
                )
            except Exception as e:
                result.errors.append(f"odds {sport} {evt['id']}: {e}")
                result.events_failed += 1
                continue

            archive.write_odds(
                root=archive_root, sport=sport,
                event_id=evt["id"], snapshot_time=snapshot_time,
                payload={"_meta": {
                    "odds_api_event": evt, "snapshot_time": snapshot_time.isoformat(),
                    "regions": regions, "markets": markets,
                }, "payload": payload},
            )
            result.events_archived += 1
            archived_in_sport += 1
            result.credits_used += usage.last_cost or 0

        if limit is not None and archived_in_sport >= limit:
            break
        cur += timedelta(days=1)

    return result
```

- [ ] **Step 4: Write CLI shell**

`apps/odds-pipeline/odds_pipeline/cli.py`:
```python
"""odds_pipeline CLI: init | pull-odds | pull-results | build | status."""
import argparse
import json
import sqlite3
import sys
from datetime import date, datetime
from dateutil import parser as dtparser

from odds_pipeline import config, archive
from odds_pipeline.odds_source.client import TheOddsApiClient
from odds_pipeline.odds_source import ingest as odds_ingest
from odds_pipeline.store import migrate, seed


def _cmd_init(args):
    migrate.init_db(config.DB_PATH)
    seed.seed_all(config.DB_PATH)
    print(f"Initialized {config.DB_PATH}")


def _cmd_pull_odds(args):
    if not config.THE_ODDS_API_KEY:
        sys.exit("THE_ODDS_API_KEY env var not set")
    client = TheOddsApiClient(config.THE_ODDS_API_KEY)
    sports = [s.strip() for s in args.sport.split(",")]
    date_from = dtparser.isoparse(args.date_from).date()
    date_to = dtparser.isoparse(args.date_to).date()

    conn = sqlite3.connect(config.DB_PATH)
    for sport in sports:
        started = datetime.utcnow().isoformat()
        result = odds_ingest.pull_odds_for_sport(
            client=client, sport=sport,
            date_from=date_from, date_to=date_to,
            regions=config.REGIONS, archive_root=config.RAW_ODDS_DIR,
            limit=args.limit,
        )
        completed = datetime.utcnow().isoformat()
        status = "ok" if not result.errors else "partial"
        conn.execute(
            "INSERT INTO ingest_runs (run_type, sport, params_json, credits_used, "
            "started_at, completed_at, status, error_message) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("odds_historical", sport, json.dumps({"from": args.date_from, "to": args.date_to, "limit": args.limit}),
             result.credits_used, started, completed, status, "; ".join(result.errors)[:500] or None),
        )
        conn.commit()
        print(f"[{sport}] processed={result.events_processed} archived={result.events_archived} "
              f"skipped={result.events_skipped} failed={result.events_failed} credits={result.credits_used}")
    conn.close()


def _cmd_pull_results(args):
    print("pull-results: stub — implemented in later task")


def _cmd_build(args):
    print("build: stub — implemented in later task")


def _cmd_status(args):
    conn = sqlite3.connect(config.DB_PATH)
    games = conn.execute("SELECT sport, COUNT(*) FROM games GROUP BY sport").fetchall()
    print("Games in DB:", dict(games))
    runs = conn.execute(
        "SELECT sport, run_type, status, credits_used, completed_at "
        "FROM ingest_runs ORDER BY run_id DESC LIMIT 10"
    ).fetchall()
    for r in runs:
        print(r)
    conn.close()


def main(argv=None):
    p = argparse.ArgumentParser(prog="odds_pipeline")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init")

    p_odds = sub.add_parser("pull-odds")
    p_odds.add_argument("--sport", required=True, help="Comma-separated, e.g. NBA,NFL")
    p_odds.add_argument("--from", dest="date_from", required=True)
    p_odds.add_argument("--to", dest="date_to", required=True)
    p_odds.add_argument("--limit", type=int, default=None)

    p_res = sub.add_parser("pull-results")
    p_res.add_argument("--sport", required=True)
    p_res.add_argument("--from", dest="date_from", required=True)
    p_res.add_argument("--to", dest="date_to", required=True)

    sub.add_parser("build")
    sub.add_parser("status")

    args = p.parse_args(argv)
    {"init": _cmd_init, "pull-odds": _cmd_pull_odds,
     "pull-results": _cmd_pull_results, "build": _cmd_build,
     "status": _cmd_status}[args.cmd](args)
```

- [ ] **Step 5: Run test to verify it passes**

```
pytest tests/test_odds_ingest.py -v
```
Expected: 3 passing.

- [ ] **Step 6: Sanity-check the CLI end-to-end (manual)**

```
python -m odds_pipeline init
```
Expected: `Initialized data/odds_pipeline.db`. Verify file exists.

```
python -m odds_pipeline pull-odds --sport NBA --from 2025-01-15 --to 2025-01-15 --limit 1
```
Expected: prints `[NBA] processed=N archived=1 skipped=0 ...`. Verify one JSON archived under `data/raw/odds/NBA/2025-01-15/`. Inspect file — it should contain real odds with Pinnacle and/or US books. **Note credits_used reported, compare to expectation** (~14 if 1×, ~140 if 10×) — this resolves Open Question #1 from the spec.

- [ ] **Step 7: Commit**

```bash
git add apps/odds-pipeline/odds_pipeline/odds_source/ingest.py apps/odds-pipeline/odds_pipeline/cli.py apps/odds-pipeline/tests/test_odds_ingest.py
git commit -m "feat(odds-pipeline): odds ingest service and pull-odds CLI"
```

---

## Task 8: ResultsAdapter Base + GameResult Dataclass

**Files:**
- Create: `apps/odds-pipeline/odds_pipeline/results_sources/__init__.py`
- Create: `apps/odds-pipeline/odds_pipeline/results_sources/base.py`
- Create: `apps/odds-pipeline/tests/test_results_base.py`

- [ ] **Step 1: Write the failing test**

`apps/odds-pipeline/tests/test_results_base.py`:
```python
from datetime import datetime, date
import pytest
from odds_pipeline.results_sources.base import ResultsAdapter, GameResult


def test_game_result_requires_segment_scores_for_full():
    r = GameResult(
        sport="NBA",
        commence_time=datetime(2025, 1, 15, 19, 30),
        home_team_canonical="LAL", away_team_canonical="BOS",
        source_game_id="0022400500",
        segment_scores={"FULL": (108, 102), "Q1": (24, 28),
                        "Q2": (30, 22), "Q3": (28, 26), "Q4": (26, 26),
                        "H1": (54, 50), "H2": (54, 52)},
        went_to_ot=False,
        raw_payload={"foo": "bar"},
    )
    assert r.segment_scores["FULL"] == (108, 102)


def test_adapter_is_abstract():
    with pytest.raises(TypeError):
        ResultsAdapter()
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_results_base.py -v
```
Expected: import errors.

- [ ] **Step 3: Write base.py**

`apps/odds-pipeline/odds_pipeline/results_sources/base.py`:
```python
"""Base interface for per-sport results adapters."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, date


@dataclass
class GameResult:
    sport: str
    commence_time: datetime
    home_team_canonical: str
    away_team_canonical: str
    source_game_id: str
    segment_scores: dict[str, tuple[int, int]]   # {'Q1': (24,28), 'FULL': (108,102), ...}
    went_to_ot: bool
    raw_payload: dict = field(default_factory=dict)


class ResultsAdapter(ABC):
    sport: str = ""
    segments: list[str] = []

    @abstractmethod
    def fetch_completed_games(self, date_from: date, date_to: date) -> list[GameResult]:
        ...
```

`apps/odds-pipeline/odds_pipeline/results_sources/__init__.py`:
```python
"""Per-sport results adapters."""
```

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/test_results_base.py -v
```
Expected: 2 passing.

- [ ] **Step 5: Commit**

```bash
git add apps/odds-pipeline/odds_pipeline/results_sources/ apps/odds-pipeline/tests/test_results_base.py
git commit -m "feat(odds-pipeline): ResultsAdapter base and GameResult dataclass"
```

---

## Task 9: NBA Results Adapter

**Files:**
- Create: `apps/odds-pipeline/odds_pipeline/results_sources/nba.py`
- Create: `apps/odds-pipeline/tests/test_results_nba.py`
- Create: `apps/odds-pipeline/tests/fixtures/results/nba/boxscore_0022400500.json`

- [ ] **Step 1: Capture fixture from nba_api (one-time)**

In a Python REPL:
```python
from nba_api.stats.endpoints import boxscoresummaryv2, leaguegamefinder
# Find a known game in Jan 2025, e.g., a Lakers home game
games = leaguegamefinder.LeagueGameFinder(
    date_from_nullable="01/15/2025", date_to_nullable="01/15/2025",
    league_id_nullable="00",
).get_dict()
# Pick a GAME_ID, then:
bs = boxscoresummaryv2.BoxScoreSummaryV2(game_id="0022400500").get_dict()
import json
open("tests/fixtures/results/nba/boxscore_0022400500.json","w").write(json.dumps(bs, indent=2))
```
Commit the fixture.

- [ ] **Step 2: Write the failing test**

`apps/odds-pipeline/tests/test_results_nba.py`:
```python
import json
from datetime import date
from pathlib import Path
from unittest.mock import patch, MagicMock
from odds_pipeline.results_sources.nba import NBAResultsAdapter

FIX = Path(__file__).parent / "fixtures" / "results" / "nba"


def test_nba_adapter_returns_per_quarter_scores():
    boxscore_payload = json.loads((FIX / "boxscore_0022400500.json").read_text())
    games_list = [
        {"GAME_ID": "0022400500", "GAME_DATE": "2025-01-15",
         "TEAM_ABBREVIATION": "LAL", "MATCHUP": "LAL vs. BOS",
         "WL": "W", "MIN": 240},
        {"GAME_ID": "0022400500", "GAME_DATE": "2025-01-15",
         "TEAM_ABBREVIATION": "BOS", "MATCHUP": "BOS @ LAL",
         "WL": "L", "MIN": 240},
    ]
    with patch("odds_pipeline.results_sources.nba._list_games", return_value=games_list), \
         patch("odds_pipeline.results_sources.nba._fetch_boxscore", return_value=boxscore_payload):
        adapter = NBAResultsAdapter()
        results = adapter.fetch_completed_games(date(2025, 1, 15), date(2025, 1, 15))

    assert len(results) == 1
    r = results[0]
    assert r.sport == "NBA"
    assert r.source_game_id == "0022400500"
    assert "FULL" in r.segment_scores
    assert "Q1" in r.segment_scores and "Q2" in r.segment_scores
    assert "Q3" in r.segment_scores and "Q4" in r.segment_scores
    assert "H1" in r.segment_scores and "H2" in r.segment_scores
    # H1 = Q1+Q2, H2 = Q3+Q4
    q1h, q1a = r.segment_scores["Q1"]
    q2h, q2a = r.segment_scores["Q2"]
    h1h, h1a = r.segment_scores["H1"]
    assert h1h == q1h + q2h
    assert h1a == q1a + q2a
```

- [ ] **Step 3: Run test to verify it fails**

```
pytest tests/test_results_nba.py -v
```
Expected: import error.

- [ ] **Step 4: Write nba.py**

`apps/odds-pipeline/odds_pipeline/results_sources/nba.py`:
```python
"""NBA results via nba_api: per-quarter scores from BoxScoreSummaryV2."""
from datetime import date, datetime
from dateutil import parser as dtparser

from odds_pipeline.results_sources.base import ResultsAdapter, GameResult


def _list_games(date_from: date, date_to: date) -> list[dict]:
    from nba_api.stats.endpoints import leaguegamefinder
    df_str = date_from.strftime("%m/%d/%Y")
    dt_str = date_to.strftime("%m/%d/%Y")
    result = leaguegamefinder.LeagueGameFinder(
        date_from_nullable=df_str, date_to_nullable=dt_str,
        league_id_nullable="00",
    ).get_dict()
    rs = result["resultSets"][0]
    headers = rs["headers"]
    return [dict(zip(headers, row)) for row in rs["rowSet"]]


def _fetch_boxscore(game_id: str) -> dict:
    from nba_api.stats.endpoints import boxscoresummaryv2
    return boxscoresummaryv2.BoxScoreSummaryV2(game_id=game_id).get_dict()


def _parse_line_score(box: dict) -> dict[str, tuple[int, int]]:
    """LineScore result set: per-team rows with PTS_QTR1..4 (+ PTS_OT1..n)."""
    line_score = next(rs for rs in box["resultSets"] if rs["name"] == "LineScore")
    headers = line_score["headers"]
    rows = [dict(zip(headers, r)) for r in line_score["rowSet"]]
    # rows[0] = visitor (away), rows[1] = home — per NBA Stats convention
    away_row, home_row = rows[0], rows[1]
    segments: dict[str, tuple[int, int]] = {}
    for i in range(1, 5):
        key = f"Q{i}"
        h = int(home_row[f"PTS_QTR{i}"] or 0)
        a = int(away_row[f"PTS_QTR{i}"] or 0)
        segments[key] = (h, a)
    # Overtimes
    ot_idx = 1
    while f"PTS_OT{ot_idx}" in home_row:
        h = int(home_row[f"PTS_OT{ot_idx}"] or 0)
        a = int(away_row[f"PTS_OT{ot_idx}"] or 0)
        if h or a:
            segments[f"OT{ot_idx}"] = (h, a)
        ot_idx += 1
    # Halves
    q1h, q1a = segments["Q1"]; q2h, q2a = segments["Q2"]
    q3h, q3a = segments["Q3"]; q4h, q4a = segments["Q4"]
    segments["H1"] = (q1h + q2h, q1a + q2a)
    segments["H2"] = (q3h + q4h, q3a + q4a)
    segments["FULL"] = (int(home_row["PTS"]), int(away_row["PTS"]))
    return segments


class NBAResultsAdapter(ResultsAdapter):
    sport = "NBA"
    segments = ["FULL", "Q1", "Q2", "Q3", "Q4", "H1", "H2", "OT1", "OT2", "OT3", "OT4"]

    def fetch_completed_games(self, date_from: date, date_to: date) -> list[GameResult]:
        games_rows = _list_games(date_from, date_to)
        # rows are per-team; dedupe to one row per GAME_ID
        seen = {}
        for row in games_rows:
            gid = row["GAME_ID"]
            if gid not in seen:
                seen[gid] = row

        results: list[GameResult] = []
        for gid, row in seen.items():
            box = _fetch_boxscore(gid)
            segs = _parse_line_score(box)
            went_to_ot = any(k.startswith("OT") for k in segs)
            # Identify home/away from MATCHUP string ("LAL vs. BOS" = LAL home; "@" = away)
            matchup = row["MATCHUP"]
            row_team = row["TEAM_ABBREVIATION"]
            if " vs. " in matchup:
                home, away = matchup.split(" vs. ")
            else:
                away, home = matchup.split(" @ ")
            commence = dtparser.isoparse(row["GAME_DATE"] + "T00:00:00Z")
            results.append(GameResult(
                sport="NBA",
                commence_time=commence,
                home_team_canonical=home.strip(),
                away_team_canonical=away.strip(),
                source_game_id=gid,
                segment_scores=segs,
                went_to_ot=went_to_ot,
                raw_payload=box,
            ))
        return results
```

- [ ] **Step 5: Run test to verify it passes**

```
pytest tests/test_results_nba.py -v
```
Expected: 1 passing.

- [ ] **Step 6: Commit**

```bash
git add apps/odds-pipeline/odds_pipeline/results_sources/nba.py apps/odds-pipeline/tests/test_results_nba.py apps/odds-pipeline/tests/fixtures/results/nba/
git commit -m "feat(odds-pipeline): NBA results adapter with per-quarter scores"
```

---

## Task 10: NFL Results Adapter

**Files:**
- Create: `apps/odds-pipeline/odds_pipeline/results_sources/nfl.py`
- Create: `apps/odds-pipeline/tests/test_results_nfl.py`
- Create: `apps/odds-pipeline/tests/fixtures/results/nfl/schedules_2024.json`

- [ ] **Step 1: Capture fixture (one-time)**

```python
import nfl_data_py as nfl
df = nfl.import_schedules([2024])
# Filter to playoff games in Jan 2025
import pandas as pd
sub = df[df["gameday"].between("2025-01-01", "2025-01-31")]
sub.to_json("tests/fixtures/results/nfl/schedules_2024.json", orient="records")
```

- [ ] **Step 2: Write the failing test**

`apps/odds-pipeline/tests/test_results_nfl.py`:
```python
import json
from datetime import date
from pathlib import Path
from unittest.mock import patch
import pandas as pd
from odds_pipeline.results_sources.nfl import NFLResultsAdapter

FIX = Path(__file__).parent / "fixtures" / "results" / "nfl"


def test_nfl_adapter_returns_per_quarter_scores():
    rows = json.loads((FIX / "schedules_2024.json").read_text())
    df = pd.DataFrame(rows)
    with patch("odds_pipeline.results_sources.nfl._import_schedules", return_value=df):
        adapter = NFLResultsAdapter()
        results = adapter.fetch_completed_games(date(2025, 1, 1), date(2025, 1, 31))
    assert len(results) > 0
    r = results[0]
    assert r.sport == "NFL"
    assert "FULL" in r.segment_scores
    assert "Q1" in r.segment_scores
    h1h, h1a = r.segment_scores["H1"]
    q1h, q1a = r.segment_scores["Q1"]
    q2h, q2a = r.segment_scores["Q2"]
    assert h1h == q1h + q2h
    assert h1a == q1a + q2a
```

- [ ] **Step 3: Run test to verify it fails**

```
pytest tests/test_results_nfl.py -v
```

- [ ] **Step 4: Write nfl.py**

`apps/odds-pipeline/odds_pipeline/results_sources/nfl.py`:
```python
"""NFL results via nfl_data_py (nflfastR schedules with per-quarter columns)."""
from datetime import date, datetime, timezone
import pandas as pd

from odds_pipeline.results_sources.base import ResultsAdapter, GameResult


def _import_schedules(seasons: list[int]) -> pd.DataFrame:
    import nfl_data_py as nfl
    return nfl.import_schedules(seasons)


def _row_to_result(row: pd.Series) -> GameResult:
    segs: dict[str, tuple[int, int]] = {}
    for q in range(1, 5):
        h = int(row.get(f"home_score_q{q}") or 0)
        a = int(row.get(f"away_score_q{q}") or 0)
        segs[f"Q{q}"] = (h, a)
    segs["H1"] = (segs["Q1"][0] + segs["Q2"][0], segs["Q1"][1] + segs["Q2"][1])
    segs["H2"] = (segs["Q3"][0] + segs["Q4"][0], segs["Q3"][1] + segs["Q4"][1])
    if pd.notna(row.get("overtime")) and int(row.get("overtime") or 0) == 1:
        ot_h = int(row["home_score"]) - sum(segs[f"Q{i}"][0] for i in range(1, 5))
        ot_a = int(row["away_score"]) - sum(segs[f"Q{i}"][1] for i in range(1, 5))
        if ot_h or ot_a:
            segs["OT1"] = (ot_h, ot_a)
    segs["FULL"] = (int(row["home_score"]), int(row["away_score"]))
    commence = datetime.fromisoformat(str(row["gameday"])).replace(tzinfo=timezone.utc)
    return GameResult(
        sport="NFL",
        commence_time=commence,
        home_team_canonical=str(row["home_team"]),
        away_team_canonical=str(row["away_team"]),
        source_game_id=str(row["game_id"]),
        segment_scores=segs,
        went_to_ot=bool(int(row.get("overtime") or 0)),
        raw_payload=row.to_dict(),
    )


class NFLResultsAdapter(ResultsAdapter):
    sport = "NFL"
    segments = ["FULL", "Q1", "Q2", "Q3", "Q4", "H1", "H2", "OT1"]

    def fetch_completed_games(self, date_from: date, date_to: date) -> list[GameResult]:
        seasons = list(range(date_from.year - 1, date_to.year + 1))
        df = _import_schedules(seasons)
        mask = pd.to_datetime(df["gameday"]).between(
            pd.Timestamp(date_from), pd.Timestamp(date_to)
        )
        sub = df[mask & df["home_score"].notna()]
        return [_row_to_result(r) for _, r in sub.iterrows()]
```

- [ ] **Step 5: Run test to verify it passes**

```
pytest tests/test_results_nfl.py -v
```
Expected: 1 passing.

- [ ] **Step 6: Commit**

```bash
git add apps/odds-pipeline/odds_pipeline/results_sources/nfl.py apps/odds-pipeline/tests/test_results_nfl.py apps/odds-pipeline/tests/fixtures/results/nfl/
git commit -m "feat(odds-pipeline): NFL results adapter via nfl_data_py schedules"
```

---

## Task 11: NHL Results Adapter

**Files:**
- Create: `apps/odds-pipeline/odds_pipeline/results_sources/nhl.py`
- Create: `apps/odds-pipeline/tests/test_results_nhl.py`
- Create: `apps/odds-pipeline/tests/fixtures/results/nhl/schedule_20250115.json`
- Create: `apps/odds-pipeline/tests/fixtures/results/nhl/boxscore_example.json`

- [ ] **Step 1: Capture fixtures (one-time)**

```bash
curl "https://api-web.nhle.com/v1/schedule/2025-01-15" > tests/fixtures/results/nhl/schedule_20250115.json
# Pick a gameId from the response
curl "https://api-web.nhle.com/v1/gamecenter/{gameId}/boxscore" > tests/fixtures/results/nhl/boxscore_example.json
```

- [ ] **Step 2: Write the failing test**

`apps/odds-pipeline/tests/test_results_nhl.py`:
```python
import json
from datetime import date
from pathlib import Path
from unittest.mock import patch
from odds_pipeline.results_sources.nhl import NHLResultsAdapter

FIX = Path(__file__).parent / "fixtures" / "results" / "nhl"


def test_nhl_adapter_returns_per_period_scores():
    schedule = json.loads((FIX / "schedule_20250115.json").read_text())
    box = json.loads((FIX / "boxscore_example.json").read_text())
    with patch("odds_pipeline.results_sources.nhl._fetch_schedule", return_value=schedule), \
         patch("odds_pipeline.results_sources.nhl._fetch_boxscore", return_value=box):
        adapter = NHLResultsAdapter()
        results = adapter.fetch_completed_games(date(2025, 1, 15), date(2025, 1, 15))
    assert len(results) > 0
    r = results[0]
    assert r.sport == "NHL"
    assert "FULL" in r.segment_scores
    assert "P1" in r.segment_scores
    assert "P2" in r.segment_scores
    assert "P3" in r.segment_scores
```

- [ ] **Step 3: Run test to verify it fails**

```
pytest tests/test_results_nhl.py -v
```

- [ ] **Step 4: Write nhl.py**

`apps/odds-pipeline/odds_pipeline/results_sources/nhl.py`:
```python
"""NHL results via NHL Stats API (api-web.nhle.com), no auth required."""
from datetime import date, datetime, timezone
from dateutil import parser as dtparser
import requests

from odds_pipeline.results_sources.base import ResultsAdapter, GameResult

SCHEDULE_URL = "https://api-web.nhle.com/v1/schedule/{date}"
BOXSCORE_URL = "https://api-web.nhle.com/v1/gamecenter/{game_id}/boxscore"


def _fetch_schedule(date_str: str) -> dict:
    return requests.get(SCHEDULE_URL.format(date=date_str), timeout=30).json()


def _fetch_boxscore(game_id: int | str) -> dict:
    return requests.get(BOXSCORE_URL.format(game_id=game_id), timeout=30).json()


def _parse_boxscore(box: dict) -> tuple[dict[str, tuple[int, int]], bool]:
    """Parse periodDescriptor entries from box['summary']['linescore']['byPeriod']."""
    summary = box.get("summary") or box
    linescore = summary.get("linescore") or {}
    by_period = linescore.get("byPeriod") or []
    segs: dict[str, tuple[int, int]] = {}
    went_to_ot = False
    for p in by_period:
        # periodDescriptor.number = 1..3 regulation, 4+ = OT, periodType = "REG"/"OT"/"SO"
        desc = p.get("periodDescriptor") or {}
        num = desc.get("number")
        ptype = desc.get("periodType", "REG")
        h = int(p.get("home", 0))
        a = int(p.get("away", 0))
        if ptype == "REG":
            segs[f"P{num}"] = (h, a)
        elif ptype == "OT":
            segs[f"OT{num - 3}" if num and num > 3 else "OT1"] = (h, a)
            went_to_ot = True
        elif ptype == "SO":
            segs["SO"] = (h, a)
            went_to_ot = True
    # FULL from totals
    total = linescore.get("totals", {})
    segs["FULL"] = (int(total.get("home", 0)), int(total.get("away", 0)))
    return segs, went_to_ot


class NHLResultsAdapter(ResultsAdapter):
    sport = "NHL"
    segments = ["FULL", "P1", "P2", "P3", "OT1", "SO"]

    def fetch_completed_games(self, date_from: date, date_to: date) -> list[GameResult]:
        results: list[GameResult] = []
        cur = date_from
        from datetime import timedelta
        while cur <= date_to:
            sched = _fetch_schedule(cur.isoformat())
            for game_day in sched.get("gameWeek", []):
                if game_day.get("date") != cur.isoformat():
                    continue
                for g in game_day.get("games", []):
                    if g.get("gameState") not in ("OFF", "FINAL"):
                        continue
                    box = _fetch_boxscore(g["id"])
                    segs, ot = _parse_boxscore(box)
                    commence = dtparser.isoparse(g["startTimeUTC"])
                    home = g.get("homeTeam", {}).get("abbrev", "")
                    away = g.get("awayTeam", {}).get("abbrev", "")
                    results.append(GameResult(
                        sport="NHL", commence_time=commence,
                        home_team_canonical=home, away_team_canonical=away,
                        source_game_id=str(g["id"]),
                        segment_scores=segs, went_to_ot=ot,
                        raw_payload=box,
                    ))
            cur += timedelta(days=1)
        return results
```

- [ ] **Step 5: Run test to verify it passes**

```
pytest tests/test_results_nhl.py -v
```

- [ ] **Step 6: Commit**

```bash
git add apps/odds-pipeline/odds_pipeline/results_sources/nhl.py apps/odds-pipeline/tests/test_results_nhl.py apps/odds-pipeline/tests/fixtures/results/nhl/
git commit -m "feat(odds-pipeline): NHL results adapter via NHL Stats API"
```

---

## Task 12: MLB Results Adapter

**Files:**
- Create: `apps/odds-pipeline/odds_pipeline/results_sources/mlb.py`
- Create: `apps/odds-pipeline/tests/test_results_mlb.py`
- Create: `apps/odds-pipeline/tests/fixtures/results/mlb/schedule_example.json`
- Create: `apps/odds-pipeline/tests/fixtures/results/mlb/linescore_example.json`

- [ ] **Step 1: Capture fixtures (one-time)**

```python
import statsapi
import json
sched = statsapi.schedule(start_date="2024-09-15", end_date="2024-09-15")
open("tests/fixtures/results/mlb/schedule_example.json","w").write(json.dumps(sched, indent=2, default=str))
# Pick a gamePk:
ls = statsapi.linescore(745671)  # use a real pk from sched
open("tests/fixtures/results/mlb/linescore_example.json","w").write(ls)
```

- [ ] **Step 2: Write the failing test**

`apps/odds-pipeline/tests/test_results_mlb.py`:
```python
import json
from datetime import date
from pathlib import Path
from unittest.mock import patch
from odds_pipeline.results_sources.mlb import MLBResultsAdapter

FIX = Path(__file__).parent / "fixtures" / "results" / "mlb"


def test_mlb_adapter_per_inning_and_f5():
    sched = json.loads((FIX / "schedule_example.json").read_text())
    linescore_text = (FIX / "linescore_example.json").read_text()
    with patch("odds_pipeline.results_sources.mlb._schedule", return_value=sched), \
         patch("odds_pipeline.results_sources.mlb._linescore", return_value=linescore_text), \
         patch("odds_pipeline.results_sources.mlb._linescore_data", return_value={"innings":[
             {"num": i, "home": {"runs": 1}, "away": {"runs": 0}} for i in range(1, 10)
         ], "teams": {"home": {"runs": 9}, "away": {"runs": 0}}}):
        adapter = MLBResultsAdapter()
        results = adapter.fetch_completed_games(date(2024, 9, 15), date(2024, 9, 15))
    assert len(results) > 0
    r = results[0]
    assert "FULL" in r.segment_scores
    assert "INN1" in r.segment_scores
    assert "F5" in r.segment_scores
    # F5 sum = innings 1..5
    f5h, f5a = r.segment_scores["F5"]
    inning_sum_h = sum(r.segment_scores[f"INN{i}"][0] for i in range(1, 6))
    assert f5h == inning_sum_h
```

- [ ] **Step 3: Run test to verify it fails**

```
pytest tests/test_results_mlb.py -v
```

- [ ] **Step 4: Write mlb.py**

`apps/odds-pipeline/odds_pipeline/results_sources/mlb.py`:
```python
"""MLB results via MLB-StatsAPI."""
from datetime import date, datetime, timezone
from dateutil import parser as dtparser

from odds_pipeline.results_sources.base import ResultsAdapter, GameResult


def _schedule(start_date: str, end_date: str) -> list[dict]:
    import statsapi
    return statsapi.schedule(start_date=start_date, end_date=end_date)


def _linescore(game_pk: int) -> str:
    import statsapi
    return statsapi.linescore(game_pk)


def _linescore_data(game_pk: int) -> dict:
    import statsapi
    return statsapi.get("game_linescore", {"gamePk": game_pk})


class MLBResultsAdapter(ResultsAdapter):
    sport = "MLB"
    segments = ["FULL", "INN1", "INN2", "INN3", "INN4", "INN5",
                "INN6", "INN7", "INN8", "INN9", "F5"]

    def fetch_completed_games(self, date_from: date, date_to: date) -> list[GameResult]:
        sched = _schedule(date_from.isoformat(), date_to.isoformat())
        results: list[GameResult] = []
        for g in sched:
            if g.get("status") not in ("Final", "Game Over", "Completed Early"):
                continue
            game_pk = g["game_id"]
            data = _linescore_data(game_pk)
            innings = data.get("innings") or []
            segs: dict[str, tuple[int, int]] = {}
            for inn in innings:
                num = inn.get("num")
                h = int((inn.get("home") or {}).get("runs", 0) or 0)
                a = int((inn.get("away") or {}).get("runs", 0) or 0)
                if num and 1 <= num <= 9:
                    segs[f"INN{num}"] = (h, a)
            f5_h = sum(segs.get(f"INN{i}", (0, 0))[0] for i in range(1, 6))
            f5_a = sum(segs.get(f"INN{i}", (0, 0))[1] for i in range(1, 6))
            segs["F5"] = (f5_h, f5_a)
            teams = data.get("teams") or {}
            segs["FULL"] = (
                int((teams.get("home") or {}).get("runs", 0) or 0),
                int((teams.get("away") or {}).get("runs", 0) or 0),
            )
            commence = dtparser.isoparse(g["game_datetime"]).astimezone(timezone.utc)
            results.append(GameResult(
                sport="MLB",
                commence_time=commence,
                home_team_canonical=g["home_name"],
                away_team_canonical=g["away_name"],
                source_game_id=str(game_pk),
                segment_scores=segs,
                went_to_ot=len(innings) > 9,
                raw_payload={"schedule": g, "linescore": data},
            ))
        return results
```

- [ ] **Step 5: Run test to verify it passes**

```
pytest tests/test_results_mlb.py -v
```

- [ ] **Step 6: Commit**

```bash
git add apps/odds-pipeline/odds_pipeline/results_sources/mlb.py apps/odds-pipeline/tests/test_results_mlb.py apps/odds-pipeline/tests/fixtures/results/mlb/
git commit -m "feat(odds-pipeline): MLB results adapter with per-inning + F5"
```

---

## Task 13: NCAAB Results Adapter

**Files:**
- Create: `apps/odds-pipeline/odds_pipeline/results_sources/ncaab.py`
- Create: `apps/odds-pipeline/tests/test_results_ncaab.py`
- Create: `apps/odds-pipeline/tests/fixtures/results/ncaab/scoreboard_example.json`

- [ ] **Step 1: Capture fixture (one-time)**

```bash
# ESPN scoreboard JSON (no auth)
curl "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard?dates=20250115" \
  > tests/fixtures/results/ncaab/scoreboard_example.json
```

- [ ] **Step 2: Write the failing test**

`apps/odds-pipeline/tests/test_results_ncaab.py`:
```python
import json
from datetime import date
from pathlib import Path
from unittest.mock import patch
from odds_pipeline.results_sources.ncaab import NCAABResultsAdapter

FIX = Path(__file__).parent / "fixtures" / "results" / "ncaab"


def test_ncaab_adapter_per_half_scores():
    payload = json.loads((FIX / "scoreboard_example.json").read_text())
    with patch("odds_pipeline.results_sources.ncaab._fetch_scoreboard", return_value=payload):
        adapter = NCAABResultsAdapter()
        results = adapter.fetch_completed_games(date(2025, 1, 15), date(2025, 1, 15))
    assert len(results) > 0
    r = results[0]
    assert "FULL" in r.segment_scores
    assert "H1" in r.segment_scores
    assert "H2" in r.segment_scores
```

- [ ] **Step 3: Run test to verify it fails**

```
pytest tests/test_results_ncaab.py -v
```

- [ ] **Step 4: Write ncaab.py**

`apps/odds-pipeline/odds_pipeline/results_sources/ncaab.py`:
```python
"""NCAAB results via ESPN scoreboard JSON."""
from datetime import date, datetime, timezone, timedelta
from dateutil import parser as dtparser
import requests

from odds_pipeline.results_sources.base import ResultsAdapter, GameResult

URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard"


def _fetch_scoreboard(date_str: str) -> dict:
    return requests.get(URL, params={"dates": date_str}, timeout=30).json()


def _parse_event(evt: dict) -> GameResult | None:
    competition = evt["competitions"][0]
    status = (evt.get("status") or {}).get("type", {}).get("state")
    if status != "post":
        return None
    competitors = competition["competitors"]
    home = next(c for c in competitors if c["homeAway"] == "home")
    away = next(c for c in competitors if c["homeAway"] == "away")
    home_linescores = [int(x["value"]) for x in (home.get("linescores") or [])]
    away_linescores = [int(x["value"]) for x in (away.get("linescores") or [])]
    segs: dict[str, tuple[int, int]] = {}
    if len(home_linescores) >= 2 and len(away_linescores) >= 2:
        segs["H1"] = (home_linescores[0], away_linescores[0])
        segs["H2"] = (home_linescores[1], away_linescores[1])
    for i in range(2, max(len(home_linescores), len(away_linescores))):
        h = home_linescores[i] if i < len(home_linescores) else 0
        a = away_linescores[i] if i < len(away_linescores) else 0
        segs[f"OT{i - 1}"] = (h, a)
    segs["FULL"] = (int(home["score"]), int(away["score"]))
    commence = dtparser.isoparse(evt["date"])
    return GameResult(
        sport="NCAAB", commence_time=commence,
        home_team_canonical=home["team"]["abbreviation"],
        away_team_canonical=away["team"]["abbreviation"],
        source_game_id=str(evt["id"]),
        segment_scores=segs,
        went_to_ot=len(home_linescores) > 2,
        raw_payload=evt,
    )


class NCAABResultsAdapter(ResultsAdapter):
    sport = "NCAAB"
    segments = ["FULL", "H1", "H2", "OT1", "OT2"]

    def fetch_completed_games(self, date_from: date, date_to: date) -> list[GameResult]:
        results: list[GameResult] = []
        cur = date_from
        while cur <= date_to:
            payload = _fetch_scoreboard(cur.strftime("%Y%m%d"))
            for evt in payload.get("events", []):
                r = _parse_event(evt)
                if r:
                    results.append(r)
            cur += timedelta(days=1)
        return results
```

- [ ] **Step 5: Run test to verify it passes**

```
pytest tests/test_results_ncaab.py -v
```

- [ ] **Step 6: Commit**

```bash
git add apps/odds-pipeline/odds_pipeline/results_sources/ncaab.py apps/odds-pipeline/tests/test_results_ncaab.py apps/odds-pipeline/tests/fixtures/results/ncaab/
git commit -m "feat(odds-pipeline): NCAAB results adapter via ESPN scoreboard"
```

---

## Task 14: NCAAF Results Adapter

**Files:**
- Create: `apps/odds-pipeline/odds_pipeline/results_sources/ncaaf.py`
- Create: `apps/odds-pipeline/tests/test_results_ncaaf.py`
- Create: `apps/odds-pipeline/tests/fixtures/results/ncaaf/games_2024_week16.json`

- [ ] **Step 1: Capture fixture (one-time)**

```bash
# Need a free key from https://collegefootballdata.com/key
curl -H "Authorization: Bearer $CFBD_API_KEY" \
  "https://api.collegefootballdata.com/games?year=2024&week=16&division=fbs" \
  > tests/fixtures/results/ncaaf/games_2024_week16.json
```

- [ ] **Step 2: Write the failing test**

`apps/odds-pipeline/tests/test_results_ncaaf.py`:
```python
import json
from datetime import date
from pathlib import Path
from unittest.mock import patch
from odds_pipeline.results_sources.ncaaf import NCAAFResultsAdapter

FIX = Path(__file__).parent / "fixtures" / "results" / "ncaaf"


def test_ncaaf_adapter_per_quarter_scores():
    payload = json.loads((FIX / "games_2024_week16.json").read_text())
    with patch("odds_pipeline.results_sources.ncaaf._fetch_games", return_value=payload):
        adapter = NCAAFResultsAdapter()
        results = adapter.fetch_completed_games(date(2024, 12, 14), date(2024, 12, 20))
    assert len(results) > 0
    r = results[0]
    assert "FULL" in r.segment_scores
    assert "Q1" in r.segment_scores
    assert "H1" in r.segment_scores
```

- [ ] **Step 3: Run test to verify it fails**

```
pytest tests/test_results_ncaaf.py -v
```

- [ ] **Step 4: Write ncaaf.py**

`apps/odds-pipeline/odds_pipeline/results_sources/ncaaf.py`:
```python
"""NCAAF results via CollegeFootballData API."""
import os
from datetime import date, datetime, timezone
from dateutil import parser as dtparser
import requests

from odds_pipeline.results_sources.base import ResultsAdapter, GameResult

CFBD_BASE = "https://api.collegefootballdata.com"


def _fetch_games(year: int, week: int | None = None) -> list[dict]:
    key = os.environ.get("CFBD_API_KEY", "")
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    params = {"year": year, "division": "fbs"}
    if week:
        params["week"] = week
    r = requests.get(f"{CFBD_BASE}/games", params=params, headers=headers, timeout=30)
    return r.json()


def _parse_game(g: dict) -> GameResult | None:
    if g.get("completed") is not True:
        return None
    home_pts = int(g.get("home_points") or 0)
    away_pts = int(g.get("away_points") or 0)
    h_lines = g.get("home_line_scores") or []
    a_lines = g.get("away_line_scores") or []
    segs: dict[str, tuple[int, int]] = {}
    for i in range(min(4, len(h_lines), len(a_lines))):
        segs[f"Q{i+1}"] = (int(h_lines[i] or 0), int(a_lines[i] or 0))
    # Halves
    if "Q1" in segs and "Q2" in segs:
        segs["H1"] = (segs["Q1"][0] + segs["Q2"][0], segs["Q1"][1] + segs["Q2"][1])
    if "Q3" in segs and "Q4" in segs:
        segs["H2"] = (segs["Q3"][0] + segs["Q4"][0], segs["Q3"][1] + segs["Q4"][1])
    # Overtimes (5th line score onward)
    for i in range(4, len(h_lines)):
        segs[f"OT{i-3}"] = (int(h_lines[i] or 0), int(a_lines[i] or 0))
    segs["FULL"] = (home_pts, away_pts)
    commence = dtparser.isoparse(g["start_date"])
    return GameResult(
        sport="NCAAF", commence_time=commence,
        home_team_canonical=g["home_team"], away_team_canonical=g["away_team"],
        source_game_id=str(g["id"]),
        segment_scores=segs,
        went_to_ot=len(h_lines) > 4,
        raw_payload=g,
    )


class NCAAFResultsAdapter(ResultsAdapter):
    sport = "NCAAF"
    segments = ["FULL", "Q1", "Q2", "Q3", "Q4", "H1", "H2", "OT1", "OT2", "OT3"]

    def fetch_completed_games(self, date_from: date, date_to: date) -> list[GameResult]:
        # CFBD games endpoint doesn't take date range; fetch entire season then filter
        years = {date_from.year, date_to.year, date_from.year - 1}
        all_games: list[dict] = []
        for y in years:
            all_games.extend(_fetch_games(y))
        results: list[GameResult] = []
        for g in all_games:
            try:
                commence = dtparser.isoparse(g["start_date"]).date()
            except Exception:
                continue
            if date_from <= commence <= date_to:
                r = _parse_game(g)
                if r:
                    results.append(r)
        return results
```

- [ ] **Step 5: Run test to verify it passes**

```
pytest tests/test_results_ncaaf.py -v
```

- [ ] **Step 6: Commit**

```bash
git add apps/odds-pipeline/odds_pipeline/results_sources/ncaaf.py apps/odds-pipeline/tests/test_results_ncaaf.py apps/odds-pipeline/tests/fixtures/results/ncaaf/
git commit -m "feat(odds-pipeline): NCAAF results adapter via CFBD API"
```

---

## Task 15: Results Ingest Service + pull-results Command

**Files:**
- Create: `apps/odds-pipeline/odds_pipeline/results_sources/ingest.py`
- Modify: `apps/odds-pipeline/odds_pipeline/cli.py:_cmd_pull_results`
- Create: `apps/odds-pipeline/tests/test_results_ingest.py`

- [ ] **Step 1: Write the failing test**

`apps/odds-pipeline/tests/test_results_ingest.py`:
```python
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock
from odds_pipeline.results_sources import ingest
from odds_pipeline.results_sources.base import GameResult


def test_pull_results_archives_one_file_per_game(tmp_path):
    mock_adapter = MagicMock()
    mock_adapter.sport = "NBA"
    mock_adapter.fetch_completed_games.return_value = [
        GameResult(
            sport="NBA",
            commence_time=datetime(2025, 1, 15, 0, 0, tzinfo=timezone.utc),
            home_team_canonical="LAL", away_team_canonical="BOS",
            source_game_id="0022400500",
            segment_scores={"FULL": (108, 102), "Q1": (24, 28)},
            went_to_ot=False,
            raw_payload={"x": "y"},
        ),
    ]
    res = ingest.pull_results_for_sport(
        adapter=mock_adapter, sport="NBA",
        date_from=date(2025, 1, 15), date_to=date(2025, 1, 15),
        archive_root=str(tmp_path),
    )
    assert res.games_archived == 1
    archived = list((tmp_path / "NBA").glob("*.json"))
    assert len(archived) == 1


def test_pull_results_handles_adapter_exception(tmp_path):
    mock_adapter = MagicMock()
    mock_adapter.sport = "NBA"
    mock_adapter.fetch_completed_games.side_effect = RuntimeError("api down")
    res = ingest.pull_results_for_sport(
        adapter=mock_adapter, sport="NBA",
        date_from=date(2025, 1, 15), date_to=date(2025, 1, 15),
        archive_root=str(tmp_path),
    )
    assert res.games_archived == 0
    assert "api down" in (res.errors[0] if res.errors else "")
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_results_ingest.py -v
```

- [ ] **Step 3: Write ingest.py**

`apps/odds-pipeline/odds_pipeline/results_sources/ingest.py`:
```python
"""Results ingest: call the per-sport adapter and archive each GameResult as JSON."""
from dataclasses import dataclass, field
from datetime import date
import json

from odds_pipeline import archive
from odds_pipeline.identity import matcher
from odds_pipeline.results_sources.base import ResultsAdapter


@dataclass
class ResultsPullResult:
    games_archived: int = 0
    errors: list[str] = field(default_factory=list)


def pull_results_for_sport(
    *,
    adapter: ResultsAdapter,
    sport: str,
    date_from: date,
    date_to: date,
    archive_root: str,
) -> ResultsPullResult:
    result = ResultsPullResult()
    try:
        games = adapter.fetch_completed_games(date_from, date_to)
    except Exception as e:
        result.errors.append(f"{sport} fetch: {e}")
        return result

    for g in games:
        game_id = matcher.build_game_id(
            sport=sport,
            commence_time=g.commence_time,
            home=g.home_team_canonical,
            away=g.away_team_canonical,
        )
        payload = {
            "game_id": game_id,
            "sport": sport,
            "commence_time": g.commence_time.isoformat(),
            "home_team_canonical": g.home_team_canonical,
            "away_team_canonical": g.away_team_canonical,
            "source_game_id": g.source_game_id,
            "segment_scores": {k: list(v) for k, v in g.segment_scores.items()},
            "went_to_ot": g.went_to_ot,
            "raw_payload": json.loads(json.dumps(g.raw_payload, default=str)),
        }
        archive.write_results(
            root=archive_root, sport=sport, game_id=game_id, payload=payload,
        )
        result.games_archived += 1
    return result
```

- [ ] **Step 4: Wire into CLI**

In `apps/odds-pipeline/odds_pipeline/cli.py`, replace the body of `_cmd_pull_results`:
```python
def _cmd_pull_results(args):
    from odds_pipeline.results_sources import ingest as r_ingest
    from odds_pipeline.results_sources.nba import NBAResultsAdapter
    from odds_pipeline.results_sources.nfl import NFLResultsAdapter
    from odds_pipeline.results_sources.nhl import NHLResultsAdapter
    from odds_pipeline.results_sources.mlb import MLBResultsAdapter
    from odds_pipeline.results_sources.ncaab import NCAABResultsAdapter
    from odds_pipeline.results_sources.ncaaf import NCAAFResultsAdapter

    adapters = {
        "NBA": NBAResultsAdapter, "NFL": NFLResultsAdapter,
        "NHL": NHLResultsAdapter, "MLB": MLBResultsAdapter,
        "NCAAB": NCAABResultsAdapter, "NCAAF": NCAAFResultsAdapter,
    }
    sports = [s.strip() for s in args.sport.split(",")]
    date_from = dtparser.isoparse(args.date_from).date()
    date_to = dtparser.isoparse(args.date_to).date()

    conn = sqlite3.connect(config.DB_PATH)
    for sport in sports:
        adapter_cls = adapters.get(sport)
        if not adapter_cls:
            print(f"Unknown sport: {sport}")
            continue
        started = datetime.utcnow().isoformat()
        res = r_ingest.pull_results_for_sport(
            adapter=adapter_cls(), sport=sport,
            date_from=date_from, date_to=date_to,
            archive_root=config.RAW_RESULTS_DIR,
        )
        completed = datetime.utcnow().isoformat()
        status = "ok" if not res.errors else "partial"
        conn.execute(
            "INSERT INTO ingest_runs (run_type, sport, params_json, credits_used, "
            "started_at, completed_at, status, error_message) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("results_fetch", sport,
             json.dumps({"from": args.date_from, "to": args.date_to}),
             None, started, completed, status, "; ".join(res.errors)[:500] or None),
        )
        conn.commit()
        print(f"[{sport}] results archived={res.games_archived}")
    conn.close()
```

- [ ] **Step 5: Run test to verify it passes**

```
pytest tests/test_results_ingest.py -v
```

- [ ] **Step 6: Commit**

```bash
git add apps/odds-pipeline/odds_pipeline/results_sources/ingest.py apps/odds-pipeline/odds_pipeline/cli.py apps/odds-pipeline/tests/test_results_ingest.py
git commit -m "feat(odds-pipeline): results ingest service and pull-results CLI"
```

---

## Task 16: Derive Layer (raw → SQLite)

**Files:**
- Create: `apps/odds-pipeline/odds_pipeline/store/derive.py`
- Modify: `apps/odds-pipeline/odds_pipeline/cli.py:_cmd_build`
- Create: `apps/odds-pipeline/tests/test_derive.py`

- [ ] **Step 1: Write the failing test**

`apps/odds-pipeline/tests/test_derive.py`:
```python
import json
import sqlite3
from pathlib import Path
from odds_pipeline.store import migrate, seed, derive


def test_derive_populates_games_from_odds_archive(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    migrate.init_db(str(db_path))
    seed.seed_all(str(db_path))

    odds_root = tmp_path / "raw" / "odds"
    results_root = tmp_path / "raw" / "results"
    (odds_root / "NBA" / "2025-01-16").mkdir(parents=True)
    (results_root / "NBA").mkdir(parents=True)

    # Fixture: minimal odds payload (single book, single market)
    odds_payload = {
        "_meta": {
            "odds_api_event": {
                "id": "evt-1",
                "commence_time": "2025-01-16T01:00:00Z",
                "home_team": "Los Angeles Lakers",
                "away_team": "Boston Celtics",
            },
            "snapshot_time": "2025-01-16T00:55:00Z",
            "regions": ["us"], "markets": ["h2h"],
        },
        "payload": {
            "id": "evt-1",
            "commence_time": "2025-01-16T01:00:00Z",
            "home_team": "Los Angeles Lakers",
            "away_team": "Boston Celtics",
            "bookmakers": [
                {"key": "draftkings", "title": "DraftKings",
                 "markets": [{"key": "h2h", "outcomes": [
                     {"name": "Los Angeles Lakers", "price": -150},
                     {"name": "Boston Celtics", "price": 130},
                 ]}]},
            ],
        },
    }
    (odds_root / "NBA" / "2025-01-16" / "evt-1__20250116T005500Z.json").write_text(
        json.dumps(odds_payload)
    )

    results_payload = {
        "game_id": "NBA:20250116:BOS@LAL",
        "sport": "NBA",
        "commence_time": "2025-01-16T01:00:00Z",
        "home_team_canonical": "LAL",
        "away_team_canonical": "BOS",
        "source_game_id": "0022400500",
        "segment_scores": {"FULL": [108, 102], "Q1": [24, 28]},
        "went_to_ot": False,
        "raw_payload": {},
    }
    (results_root / "NBA" / "NBA:20250116:BOS@LAL.json").write_text(
        json.dumps(results_payload)
    )

    derive.build_all(db_path=str(db_path),
                     odds_root=str(odds_root),
                     results_root=str(results_root))

    conn = sqlite3.connect(db_path)
    games = conn.execute("SELECT game_id, home_team, away_team FROM games").fetchall()
    assert ("NBA:20250116:BOS@LAL", "LAL", "BOS") in games

    odds_rows = conn.execute(
        "SELECT bookmaker_key, market_type, side, price_american, is_close "
        "FROM odds_snapshots WHERE game_id=?",
        ("NBA:20250116:BOS@LAL",),
    ).fetchall()
    assert ("draftkings", "h2h", "home", -150, 1) in odds_rows
    assert ("draftkings", "h2h", "away", 130, 1) in odds_rows

    scores = conn.execute(
        "SELECT segment_key, home_score, away_score FROM scores WHERE game_id=?",
        ("NBA:20250116:BOS@LAL",),
    ).fetchall()
    assert ("FULL", 108, 102) in scores
    assert ("Q1", 24, 28) in scores


def test_derive_is_idempotent(tmp_path):
    db_path = tmp_path / "test.db"
    migrate.init_db(str(db_path))
    seed.seed_all(str(db_path))
    odds_root = tmp_path / "raw" / "odds"
    odds_root.mkdir(parents=True)
    results_root = tmp_path / "raw" / "results"
    results_root.mkdir(parents=True)
    derive.build_all(db_path=str(db_path), odds_root=str(odds_root), results_root=str(results_root))
    derive.build_all(db_path=str(db_path), odds_root=str(odds_root), results_root=str(results_root))
    # No exception = pass
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_derive.py -v
```

- [ ] **Step 3: Write derive.py**

`apps/odds-pipeline/odds_pipeline/store/derive.py`:
```python
"""Build derived SQLite tables from raw JSON archive."""
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from dateutil import parser as dtparser

from odds_pipeline.identity import matcher

MARKET_SEGMENT_MAP = {
    "h2h": "FULL", "spreads": "FULL", "totals": "FULL",
    "h2h_q1": "Q1", "spreads_q1": "Q1", "totals_q1": "Q1",
    "h2h_q2": "Q2", "spreads_q2": "Q2", "totals_q2": "Q2",
    "h2h_q3": "Q3", "spreads_q3": "Q3", "totals_q3": "Q3",
    "h2h_q4": "Q4", "spreads_q4": "Q4", "totals_q4": "Q4",
    "h2h_h1": "H1", "spreads_h1": "H1", "totals_h1": "H1",
    "h2h_h2": "H2", "spreads_h2": "H2", "totals_h2": "H2",
    "spreads_p1": "P1", "totals_p1": "P1",
    "spreads_p2": "P2", "totals_p2": "P2",
    "spreads_p3": "P3", "totals_p3": "P3",
    "spreads_1st_5_innings": "F5", "totals_1st_5_innings": "F5",
}


def _market_type_for(market_key: str) -> str:
    if market_key.startswith("h2h"):
        return "h2h"
    if market_key.startswith("spreads"):
        return "spreads"
    if market_key.startswith("totals"):
        return "totals"
    return market_key


def _outcome_side(market_type: str, name: str, home: str, away: str) -> str:
    if market_type == "totals":
        return "over" if name.lower() == "over" else "under"
    return "home" if name == home else "away"


def _american_to_decimal(american: int) -> float:
    if american >= 100:
        return 1 + american / 100
    return 1 + 100 / abs(american)


def _clear_derived(conn):
    conn.executescript(
        "DELETE FROM odds_snapshots; DELETE FROM scores; DELETE FROM games;"
    )


def _ingest_odds_file(conn, sport: str, path: Path):
    data = json.loads(path.read_text())
    meta = data["_meta"]
    payload = data["payload"]
    snapshot_time = meta["snapshot_time"]
    commence = dtparser.isoparse(payload["commence_time"])

    home_raw = payload["home_team"]
    away_raw = payload["away_team"]
    home = matcher.canonical_team(sport, home_raw)
    away = matcher.canonical_team(sport, away_raw)
    game_id = matcher.build_game_id(sport, commence, home, away)

    now = datetime.utcnow().isoformat()
    conn.execute(
        "INSERT OR IGNORE INTO games (game_id, sport, commence_time, home_team, away_team, "
        "odds_api_event_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (game_id, sport, commence.isoformat(), home, away,
         payload.get("id"), now, now),
    )

    rel_path = str(path)
    for bm in payload.get("bookmakers", []):
        book_key = bm["key"]
        for market in bm.get("markets", []):
            mkey = market["key"]
            mtype = _market_type_for(mkey)
            segment = MARKET_SEGMENT_MAP.get(mkey, "FULL")
            for outcome in market.get("outcomes", []):
                side = _outcome_side(mtype, outcome["name"], payload["home_team"], payload["away_team"])
                line = outcome.get("point")
                price = int(outcome["price"])
                conn.execute(
                    "INSERT INTO odds_snapshots (game_id, bookmaker_key, segment_key, market_type, "
                    "side, line, price_american, price_decimal, snapshot_time, is_close, raw_archive_path) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)",
                    (game_id, book_key, segment, mtype, side, line,
                     price, _american_to_decimal(price), snapshot_time, rel_path),
                )


def _ingest_results_file(conn, sport: str, path: Path):
    data = json.loads(path.read_text())
    game_id = data["game_id"]
    commence = dtparser.isoparse(data["commence_time"])
    home = data["home_team_canonical"]
    away = data["away_team_canonical"]
    now = datetime.utcnow().isoformat()
    conn.execute(
        "INSERT OR IGNORE INTO games (game_id, sport, commence_time, home_team, away_team, "
        "results_source_game_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (game_id, sport, commence.isoformat(), home, away,
         data.get("source_game_id"), now, now),
    )
    conn.execute(
        "UPDATE games SET results_source_game_id=COALESCE(results_source_game_id, ?), "
        "updated_at=? WHERE game_id=?",
        (data.get("source_game_id"), now, game_id),
    )
    rel_path = str(path)
    for seg, (h_score, a_score) in data["segment_scores"].items():
        conn.execute(
            "INSERT OR REPLACE INTO scores (game_id, segment_key, home_score, away_score, raw_archive_path) "
            "VALUES (?, ?, ?, ?, ?)",
            (game_id, seg, int(h_score), int(a_score), rel_path),
        )


def build_all(*, db_path: str, odds_root: str, results_root: str):
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = OFF")
    _clear_derived(conn)
    odds_path = Path(odds_root)
    if odds_path.exists():
        for sport_dir in odds_path.iterdir():
            if not sport_dir.is_dir():
                continue
            sport = sport_dir.name
            for f in sport_dir.rglob("*.json"):
                _ingest_odds_file(conn, sport, f)
    results_path = Path(results_root)
    if results_path.exists():
        for sport_dir in results_path.iterdir():
            if not sport_dir.is_dir():
                continue
            sport = sport_dir.name
            for f in sport_dir.glob("*.json"):
                _ingest_results_file(conn, sport, f)
    conn.commit()
    conn.close()
```

- [ ] **Step 4: Wire into CLI**

Replace `_cmd_build` body in `cli.py`:
```python
def _cmd_build(args):
    from odds_pipeline.store import derive
    derive.build_all(
        db_path=config.DB_PATH,
        odds_root=config.RAW_ODDS_DIR,
        results_root=config.RAW_RESULTS_DIR,
    )
    conn = sqlite3.connect(config.DB_PATH)
    games_count = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    odds_count = conn.execute("SELECT COUNT(*) FROM odds_snapshots").fetchone()[0]
    scores_count = conn.execute("SELECT COUNT(*) FROM scores").fetchone()[0]
    print(f"games={games_count} odds_snapshots={odds_count} scores={scores_count}")
    # Unmatched: games with no scores
    unmatched = conn.execute(
        "SELECT game_id FROM games WHERE game_id NOT IN (SELECT DISTINCT game_id FROM scores) "
        "AND results_source_game_id IS NULL LIMIT 10"
    ).fetchall()
    if unmatched:
        print(f"Unmatched (no scores) sample: {[u[0] for u in unmatched]}")
    conn.close()
```

- [ ] **Step 5: Run test to verify it passes**

```
pytest tests/test_derive.py -v
```

- [ ] **Step 6: Commit**

```bash
git add apps/odds-pipeline/odds_pipeline/store/derive.py apps/odds-pipeline/odds_pipeline/cli.py apps/odds-pipeline/tests/test_derive.py
git commit -m "feat(odds-pipeline): derive raw archive into SQLite tables"
```

---

## Task 17: Sample Run + Status Polish

**Files:**
- Modify: `apps/odds-pipeline/odds_pipeline/cli.py:_cmd_status`
- Update: `apps/odds-pipeline/TODO.md`

This task has no new test — it is an end-to-end validation of the entire pipeline against real APIs.

- [ ] **Step 1: Improve status to show credit balance + ingest summary**

Replace `_cmd_status` body in `cli.py`:
```python
def _cmd_status(args):
    import requests
    conn = sqlite3.connect(config.DB_PATH)
    print("=== DB summary ===")
    games = dict(conn.execute("SELECT sport, COUNT(*) FROM games GROUP BY sport").fetchall())
    odds = dict(conn.execute(
        "SELECT g.sport, COUNT(*) FROM odds_snapshots o JOIN games g ON g.game_id=o.game_id "
        "GROUP BY g.sport"
    ).fetchall())
    scores = dict(conn.execute(
        "SELECT g.sport, COUNT(*) FROM scores s JOIN games g ON g.game_id=s.game_id "
        "GROUP BY g.sport"
    ).fetchall())
    for sport in ("NBA","NFL","NHL","MLB","NCAAB","NCAAF"):
        print(f"  {sport}: games={games.get(sport,0)} odds_rows={odds.get(sport,0)} scores_rows={scores.get(sport,0)}")

    unmatched = conn.execute(
        "SELECT COUNT(*) FROM games WHERE game_id NOT IN (SELECT DISTINCT game_id FROM scores)"
    ).fetchone()[0]
    print(f"  Games missing scores: {unmatched}")

    print("\n=== Recent ingest_runs ===")
    for r in conn.execute(
        "SELECT run_type, sport, status, credits_used, completed_at FROM ingest_runs "
        "ORDER BY run_id DESC LIMIT 10"
    ):
        print(f"  {r}")
    conn.close()

    if config.THE_ODDS_API_KEY:
        try:
            r = requests.get(
                "https://api.the-odds-api.com/v4/sports",
                params={"apiKey": config.THE_ODDS_API_KEY}, timeout=10,
            )
            used = r.headers.get("x-requests-used")
            remaining = r.headers.get("x-requests-remaining")
            print(f"\n=== The Odds API quota ===\n  used={used} remaining={remaining}")
        except Exception as e:
            print(f"  (quota check failed: {e})")
```

- [ ] **Step 2: Execute the sample run end-to-end**

```
cd apps/odds-pipeline
python -m odds_pipeline init
python -m odds_pipeline pull-odds --sport NBA,NFL,NHL,NCAAF --from 2025-01-01 --to 2025-01-31 --limit 10
python -m odds_pipeline pull-results --sport NBA,NFL,NHL,NCAAF --from 2025-01-01 --to 2025-01-31
python -m odds_pipeline build
python -m odds_pipeline status
```

Expected:
- `pull-odds` reports archived=10 per sport, credits_used printed
- `pull-results` reports games archived per sport
- `build` reports `games=~40 odds_snapshots>0 scores>0`
- `status` shows quota remaining and per-sport breakdown

Inspect the DB:
```
python -c "import sqlite3; c=sqlite3.connect('data/odds_pipeline.db'); \
  print(c.execute('SELECT g.game_id, o.bookmaker_key, o.segment_key, o.market_type, o.side, o.line, o.price_american FROM games g JOIN odds_snapshots o ON g.game_id=o.game_id WHERE g.sport=\"NBA\" LIMIT 20').fetchall())"
```

- [ ] **Step 3: Resolve spec open questions from the sample**

After the sample run, document findings in `TODO.md` under `Done`:
- Per-event historical credit cost: 1× or 10×? (from `credits_used` in `ingest_runs`)
- Did Pinnacle return segment markets? (query `odds_snapshots WHERE bookmaker_key='pinnacle' AND segment_key != 'FULL'`)
- Are `spreads_p1`/`totals_p1` the correct NHL market keys? (check `odds_snapshots WHERE g.sport='NHL' AND segment_key='P1'`)
- Sample of unmatched games — what team-name aliases need adding?

If team aliases need adding, edit `identity/aliases/{sport}.json` and re-run `build` (no re-pull needed).

- [ ] **Step 4: Update TODO.md**

```markdown
# TODO — odds-pipeline

## Now
- [ ] Add team aliases for any unmatched games surfaced by sample run

## Next
- [ ] Forward-collection cron (calls pull-odds with live `/odds` endpoint daily)
- [ ] Multi-snapshot ingestion (opening, 24h, 1h, close per game)
- [ ] Alt-line markets (`is_alternate` flag on odds_snapshots)

## Backlog
- Player props ingestion (separate pipeline)
- Sharp-book alternative if a Pinnacle-equivalent emerges

## Done
- 2026-05-24: v1 framework + January 2025 sample run validated
```

- [ ] **Step 5: Commit**

```bash
git add apps/odds-pipeline/odds_pipeline/cli.py apps/odds-pipeline/TODO.md
git commit -m "feat(odds-pipeline): status command polish and sample-run results"
```

---

## Final Verification

- [ ] All tests pass:
```
cd apps/odds-pipeline
pytest -v
```
- [ ] `python -m odds_pipeline status` prints a coherent summary.
- [ ] Sample SQLite has expected row counts and at least one game per sport with both odds and scores.
- [ ] `data/raw/` archive is intact and re-runnable via `build` alone.
