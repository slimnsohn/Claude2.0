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
