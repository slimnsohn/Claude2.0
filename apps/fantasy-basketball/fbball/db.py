"""DuckDB storage for the NBA game-log data lake.

The store is the source of truth. Every write is idempotent on
(player_id, game_id) so re-running ingestion can never create duplicates.
"""

import duckdb

SCHEMA = """
CREATE TABLE IF NOT EXISTS game_logs (
    player_id   INTEGER,
    player_name VARCHAR,
    team        VARCHAR,
    season      VARCHAR,
    season_type VARCHAR,
    game_id     VARCHAR,
    game_date   DATE,
    min         DOUBLE,
    fgm DOUBLE, fga DOUBLE,
    ftm DOUBLE, fta DOUBLE,
    fg3m        DOUBLE,
    pts DOUBLE, reb DOUBLE, ast DOUBLE,
    stl DOUBLE, blk DOUBLE, tov DOUBLE,
    PRIMARY KEY (player_id, game_id)
);

CREATE TABLE IF NOT EXISTS players (
    player_id    INTEGER PRIMARY KEY,
    full_name    VARCHAR,
    is_active    BOOLEAN,
    nba_position VARCHAR,   -- G/F/C from current team rosters (active only)
    team         VARCHAR,   -- current team abbreviation
    positions    VARCHAR    -- Yahoo eligibility, filled in Component 2
);

CREATE TABLE IF NOT EXISTS teams (
    team_id      INTEGER PRIMARY KEY,
    abbreviation VARCHAR,
    full_name    VARCHAR,
    city         VARCHAR,
    nickname     VARCHAR
);

-- Yahoo league side (kept decoupled from NBA stats; joins at nba_player_id).
CREATE TABLE IF NOT EXISTS yahoo_teams (
    team_key   VARCHAR PRIMARY KEY,
    league_key VARCHAR,
    name       VARCHAR,
    manager    VARCHAR,
    is_my_team BOOLEAN
);

CREATE TABLE IF NOT EXISTS yahoo_roster (
    team_key           VARCHAR,
    player_key         VARCHAR,
    player_name        VARCHAR,
    editorial_team     VARCHAR,   -- NBA team abbr, per Yahoo
    selected_position  VARCHAR,   -- where they're slotted right now
    eligible_positions VARCHAR,   -- comma-joined Yahoo eligibility
    status             VARCHAR,   -- INJ / O / GTD / ''
    nba_player_id      INTEGER,   -- bridge to game_logs/players (filled by matcher)
    PRIMARY KEY (team_key, player_key)
);

CREATE TABLE IF NOT EXISTS yahoo_free_agents (
    league_key         VARCHAR,
    player_key         VARCHAR PRIMARY KEY,
    player_name        VARCHAR,
    editorial_team     VARCHAR,
    eligible_positions VARCHAR,
    status             VARCHAR,
    nba_player_id      INTEGER
);

-- ── Yahoo league HISTORY lake (fixed; one immutable set per past season) ──
CREATE TABLE IF NOT EXISTS yh_seasons (
    season     INTEGER PRIMARY KEY,   -- 2010 .. 2025
    league_key VARCHAR,
    name       VARCHAR,
    num_teams  INTEGER,
    start_date DATE,
    end_date   DATE
);

CREATE TABLE IF NOT EXISTS yh_teams (
    season           INTEGER,
    team_key         VARCHAR,
    team_name        VARCHAR,
    manager_nickname VARCHAR,
    manager_email    VARCHAR,   -- owner identity (owners change; email is stable)
    manager_guid     VARCHAR,
    PRIMARY KEY (season, team_key)
);

CREATE TABLE IF NOT EXISTS yh_standings (
    season              INTEGER,
    team_key            VARCHAR,
    final_rank          INTEGER,   -- reflects playoffs (championship result)
    playoff_seed        INTEGER,   -- regular-season seed (playoff teams)
    regular_season_rank INTEGER,   -- derived: full reg-season order, ALL teams
    wins                INTEGER,
    losses              INTEGER,
    ties                INTEGER,
    win_pct             DOUBLE,
    games_back          VARCHAR,
    points_for          VARCHAR,
    PRIMARY KEY (season, team_key)
);

CREATE TABLE IF NOT EXISTS yh_draft (
    season      INTEGER,
    pick        INTEGER,
    round       INTEGER,
    team_key    VARCHAR,
    player_key  VARCHAR,
    player_name VARCHAR,
    PRIMARY KEY (season, pick)
);

CREATE TABLE IF NOT EXISTS yh_final_roster (
    season             INTEGER,
    team_key           VARCHAR,
    player_key         VARCHAR,
    player_name        VARCHAR,
    eligible_positions VARCHAR,
    status             VARCHAR,
    PRIMARY KEY (season, team_key, player_key)
);

-- Canonical owner identity (derived): one owner across renames + email changes,
-- prioritizing team-name continuity. Rebuilt wholesale from yh_teams.
CREATE TABLE IF NOT EXISTS yh_owner_identity (
    season      INTEGER,
    team_key    VARCHAR,
    owner_id    VARCHAR,   -- stable slug of the owner's most-used team name
    owner_label VARCHAR,   -- that team name
    PRIMARY KEY (season, team_key)
);

CREATE TABLE IF NOT EXISTS ingest_state (
    source      VARCHAR PRIMARY KEY,
    last_season VARCHAR,
    last_date   DATE,
    updated_at  TIMESTAMP
);

-- Which historical seasons are fully loaded and immutable. The current
-- (in-progress) season is deliberately never recorded here, so it always
-- gets re-pulled. This is what makes backfill resumable in any order.
CREATE TABLE IF NOT EXISTS completed_seasons (
    season       VARCHAR PRIMARY KEY,
    completed_at TIMESTAMP
);
"""

# Derived analytics, defined as views so they always reflect current game_logs
# (no refresh step, never stale). Percentages are volume-weighted —
# total makes / total attempts — never an average of per-game percentages.
ANALYTICS_VIEWS = """
CREATE OR REPLACE VIEW player_season_stats AS
SELECT
    g.player_id,
    ANY_VALUE(p.full_name)    AS full_name,
    ANY_VALUE(p.nba_position) AS nba_position,
    ANY_VALUE(p.team)         AS team,
    g.season,
    g.season_type,
    COUNT(*)      AS gp,
    AVG(g.min)    AS mpg,
    AVG(g.pts)    AS ppg,
    AVG(g.reb)    AS rpg,
    AVG(g.ast)    AS apg,
    AVG(g.stl)    AS spg,
    AVG(g.blk)    AS bpg,
    AVG(g.tov)    AS topg,
    AVG(g.fg3m)   AS tpm_pg,
    AVG(g.fgm)    AS fgm_pg,
    AVG(g.fga)    AS fga_pg,
    AVG(g.ftm)    AS ftm_pg,
    AVG(g.fta)    AS fta_pg,
    SUM(g.fgm)    AS fgm_tot,
    SUM(g.fga)    AS fga_tot,
    SUM(g.ftm)    AS ftm_tot,
    SUM(g.fta)    AS fta_tot,
    CASE WHEN SUM(g.fga) > 0 THEN SUM(g.fgm) * 1.0 / SUM(g.fga) END AS fg_pct,
    CASE WHEN SUM(g.fta) > 0 THEN SUM(g.ftm) * 1.0 / SUM(g.fta) END AS ft_pct
FROM game_logs g
LEFT JOIN players p USING (player_id)
GROUP BY g.player_id, g.season, g.season_type;

CREATE OR REPLACE VIEW player_recent_form AS
WITH ranked AS (
    SELECT
        g.*,
        ROW_NUMBER() OVER (
            PARTITION BY g.player_id
            ORDER BY g.game_date DESC, g.game_id DESC
        ) AS rn
    FROM game_logs g
    WHERE g.season = (SELECT MAX(season) FROM game_logs)
)
SELECT
    r.player_id,
    ANY_VALUE(p.full_name)    AS full_name,
    ANY_VALUE(p.nba_position) AS nba_position,
    ANY_VALUE(p.team)         AS team,
    COUNT(*)     AS gp_window,
    AVG(r.min)   AS mpg,
    AVG(r.pts)   AS ppg,
    AVG(r.reb)   AS rpg,
    AVG(r.ast)   AS apg,
    AVG(r.stl)   AS spg,
    AVG(r.blk)   AS bpg,
    AVG(r.tov)   AS topg,
    AVG(r.fg3m)  AS tpm_pg,
    AVG(r.fga)   AS fga_pg,
    AVG(r.fta)   AS fta_pg,
    SUM(r.fgm)   AS fgm_tot,
    SUM(r.fga)   AS fga_tot,
    SUM(r.ftm)   AS ftm_tot,
    SUM(r.fta)   AS fta_tot,
    CASE WHEN SUM(r.fga) > 0 THEN SUM(r.fgm) * 1.0 / SUM(r.fga) END AS fg_pct,
    CASE WHEN SUM(r.fta) > 0 THEN SUM(r.ftm) * 1.0 / SUM(r.fta) END AS ft_pct
FROM ranked r
LEFT JOIN players p USING (player_id)
WHERE r.rn <= 15
GROUP BY r.player_id;
"""

GAME_LOG_COLUMNS = [
    "player_id", "player_name", "team", "season", "season_type",
    "game_id", "game_date", "min", "fgm", "fga", "ftm", "fta",
    "fg3m", "pts", "reb", "ast", "stl", "blk", "tov",
]


def connect(path: str = ":memory:") -> duckdb.DuckDBPyConnection:
    return duckdb.connect(path)


def init_schema(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(SCHEMA)
    # Migrate stores created before reference columns existed.
    con.execute("ALTER TABLE players ADD COLUMN IF NOT EXISTS nba_position VARCHAR")
    con.execute("ALTER TABLE players ADD COLUMN IF NOT EXISTS team VARCHAR")
    # Derived analytics views (recreated each init so they track schema changes).
    con.execute(ANALYTICS_VIEWS)


def count_game_logs(con: duckdb.DuckDBPyConnection) -> int:
    return con.execute("SELECT COUNT(*) FROM game_logs").fetchone()[0]


def latest_season(con) -> str | None:
    """The most recent season present in game_logs (None if empty).

    This is what the analysis tools default to — pull last season in the
    offseason and everything points at it automatically, no year to edit.
    """
    return con.execute("SELECT MAX(season) FROM game_logs").fetchone()[0]


def upsert_game_logs(con, rows) -> int:
    """Insert game-log rows, skipping any (player_id, game_id) already present.

    Returns the number of NEW rows actually inserted.
    """
    if len(rows) == 0:
        return 0

    before = count_game_logs(con)
    # Register the dataframe and insert only rows whose PK isn't already stored.
    con.register("_incoming", rows[GAME_LOG_COLUMNS])
    con.execute(
        """
        INSERT INTO game_logs
        SELECT i.* FROM _incoming i
        WHERE NOT EXISTS (
            SELECT 1 FROM game_logs g
            WHERE g.player_id = i.player_id AND g.game_id = i.game_id
        )
        """
    )
    con.unregister("_incoming")
    return count_game_logs(con) - before


def count_teams(con) -> int:
    return con.execute("SELECT COUNT(*) FROM teams").fetchone()[0]


def count_players(con) -> int:
    return con.execute("SELECT COUNT(*) FROM players").fetchone()[0]


def upsert_teams(con, rows) -> int:
    """Insert/refresh team reference rows (idempotent on team_id)."""
    if len(rows) == 0:
        return 0
    before = count_teams(con)
    con.register("_inc_teams", rows)
    con.execute(
        """
        INSERT INTO teams BY NAME SELECT * FROM _inc_teams
        ON CONFLICT (team_id) DO UPDATE SET
            abbreviation = EXCLUDED.abbreviation,
            full_name    = EXCLUDED.full_name,
            city         = EXCLUDED.city,
            nickname     = EXCLUDED.nickname
        """
    )
    con.unregister("_inc_teams")
    return count_teams(con) - before


def upsert_players(con, rows) -> int:
    """Insert/refresh player identity rows (idempotent on player_id).

    Only identity columns (id, name, active) are written here; position/team
    are filled separately by enrich_players so re-running this never wipes them.
    """
    if len(rows) == 0:
        return 0
    before = count_players(con)
    con.register("_inc_players", rows[["player_id", "full_name", "is_active"]])
    con.execute(
        """
        INSERT INTO players (player_id, full_name, is_active)
        SELECT player_id, full_name, is_active FROM _inc_players
        ON CONFLICT (player_id) DO UPDATE SET
            full_name = EXCLUDED.full_name,
            is_active = EXCLUDED.is_active
        """
    )
    con.unregister("_inc_players")
    return count_players(con) - before


def backfill_players_from_game_logs(con, active_season: str) -> int:
    """Add any player who appears in game_logs but is missing from `players`.

    nba_api's bundled static list lags live data, so a few players with real
    game logs aren't in it. We take their identity (id, most-recent name) from
    the logs we already hold — real data, not fabricated — and mark them active
    if they have a game in `active_season`. Existing rows are left untouched.
    Returns the number of players added.
    """
    before = count_players(con)
    con.execute(
        """
        INSERT INTO players (player_id, full_name, is_active)
        SELECT
            gl.player_id,
            -- most-recent name seen for this player in the logs
            (ARRAY_AGG(gl.player_name ORDER BY gl.game_date DESC))[1],
            BOOL_OR(gl.season = ?)
        FROM game_logs gl
        WHERE gl.player_id NOT IN (SELECT player_id FROM players)
        GROUP BY gl.player_id
        """,
        [active_season],
    )
    return count_players(con) - before


def enrich_players(con, rows) -> int:
    """Set nba_position/team for players found on current rosters.

    `rows` has columns player_id, nba_position, team. Players not present are
    left untouched (NULL stays NULL — missing shown as missing). Returns the
    number of player rows updated.
    """
    if len(rows) == 0:
        return 0
    con.register("_inc_roster", rows[["player_id", "nba_position", "team"]])
    con.execute(
        """
        UPDATE players SET
            nba_position = r.nba_position,
            team         = r.team
        FROM _inc_roster r
        WHERE players.player_id = r.player_id
        """
    )
    updated = con.execute(
        "SELECT COUNT(*) FROM players p JOIN _inc_roster r USING (player_id)"
    ).fetchone()[0]
    con.unregister("_inc_roster")
    return updated


def count_yahoo_teams(con) -> int:
    return con.execute("SELECT COUNT(*) FROM yahoo_teams").fetchone()[0]


def upsert_yahoo_teams(con, rows) -> int:
    """Insert/refresh Yahoo fantasy teams (idempotent on team_key)."""
    if len(rows) == 0:
        return 0
    before = count_yahoo_teams(con)
    con.register("_inc_yteams", rows)
    con.execute(
        """
        INSERT INTO yahoo_teams BY NAME SELECT * FROM _inc_yteams
        ON CONFLICT (team_key) DO UPDATE SET
            league_key = EXCLUDED.league_key,
            name       = EXCLUDED.name,
            manager    = EXCLUDED.manager,
            is_my_team = EXCLUDED.is_my_team
        """
    )
    con.unregister("_inc_yteams")
    return count_yahoo_teams(con) - before


def upsert_yahoo_roster(con, rows) -> int:
    """Replace each team's roster with the incoming snapshot.

    A roster is a point-in-time snapshot: dropped players must disappear, so we
    delete each incoming team's existing rows before inserting. Returns the
    number of roster rows written.
    """
    if len(rows) == 0:
        return 0
    con.register("_inc_yroster", rows)
    # Clear the teams present in this snapshot, then insert fresh.
    con.execute(
        "DELETE FROM yahoo_roster WHERE team_key IN (SELECT DISTINCT team_key FROM _inc_yroster)"
    )
    con.execute("INSERT INTO yahoo_roster BY NAME SELECT * FROM _inc_yroster")
    con.unregister("_inc_yroster")
    return len(rows)


def count_free_agents(con) -> int:
    return con.execute("SELECT COUNT(*) FROM yahoo_free_agents").fetchone()[0]


def upsert_free_agents(con, rows) -> int:
    """Replace a league's free-agent pool with the incoming snapshot."""
    if len(rows) == 0:
        return 0
    con.register("_inc_fa", rows)
    con.execute(
        "DELETE FROM yahoo_free_agents WHERE league_key IN (SELECT DISTINCT league_key FROM _inc_fa)"
    )
    con.execute("INSERT INTO yahoo_free_agents BY NAME SELECT * FROM _inc_fa")
    con.unregister("_inc_fa")
    return len(rows)


_HISTORY_TABLES = {"yh_seasons", "yh_teams", "yh_standings", "yh_draft", "yh_final_roster"}


def replace_history(con, table: str, rows) -> int:
    """Write history rows, replacing any existing rows for the same season(s).

    Immutable data, but re-runnable: a re-pull of a season cleanly overwrites it.
    """
    if table not in _HISTORY_TABLES:
        raise ValueError(f"unknown history table: {table}")
    if len(rows) == 0:
        return 0
    con.register("_inc_hist", rows)
    con.execute(
        f"DELETE FROM {table} WHERE season IN (SELECT DISTINCT season FROM _inc_hist)"
    )
    con.execute(f"INSERT INTO {table} BY NAME SELECT * FROM _inc_hist")
    con.unregister("_inc_hist")
    return len(rows)


def write_owner_identity(con, rows) -> int:
    """Replace the whole owner-identity table (clusters span all seasons)."""
    con.execute("DELETE FROM yh_owner_identity")
    if len(rows) == 0:
        return 0
    con.register("_inc_own", rows)
    con.execute("INSERT INTO yh_owner_identity BY NAME SELECT * FROM _inc_own")
    con.unregister("_inc_own")
    return len(rows)


def get_checkpoint(con, source: str):
    """Return the checkpoint dict for a source, or None if never set."""
    row = con.execute(
        "SELECT source, last_season, last_date, updated_at "
        "FROM ingest_state WHERE source = ?",
        [source],
    ).fetchone()
    if row is None:
        return None
    return {
        "source": row[0],
        "last_season": row[1],
        "last_date": row[2],
        "updated_at": row[3],
    }


def is_season_complete(con, season: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM completed_seasons WHERE season = ?", [season]
    ).fetchone()
    return row is not None


def mark_season_complete(con, season: str) -> None:
    con.execute(
        """
        INSERT INTO completed_seasons (season, completed_at)
        VALUES (?, now())
        ON CONFLICT (season) DO UPDATE SET completed_at = EXCLUDED.completed_at
        """,
        [season],
    )


def set_checkpoint(con, source: str, season: str, last_date) -> None:
    """Record how far ingestion has progressed for a source (one row per source)."""
    con.execute(
        """
        INSERT INTO ingest_state (source, last_season, last_date, updated_at)
        VALUES (?, ?, ?, now())
        ON CONFLICT (source) DO UPDATE SET
            last_season = EXCLUDED.last_season,
            last_date   = EXCLUDED.last_date,
            updated_at  = EXCLUDED.updated_at
        """,
        [source, season, last_date],
    )
