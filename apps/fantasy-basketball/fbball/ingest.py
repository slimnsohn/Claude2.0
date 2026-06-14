"""Orchestration: pull -> normalize -> store, resumably.

Two modes:
  backfill(seasons) — one-time historical load. Resumable: seasons at or
                      below the checkpoint high-water mark are skipped.
  update(season)    — nightly incremental for the current season. Idempotent
                      upsert means only genuinely new games land.
"""

from fbball import db, nba_source, transform

SOURCE = "nba_game_logs"


def _max_date(rows):
    """Latest game_date in a normalized frame, or None if empty."""
    if len(rows) == 0:
        return None
    return rows["game_date"].max()


def load_reference(
    con,
    *,
    players=None,
    teams=None,
    fetch_team_roster=None,
    sleep=None,
    rate_limit: float = nba_source.RATE_LIMIT_SECONDS,
) -> dict:
    """Populate the teams + players reference tables.

    teams/players default to nba_api's bundled static data (no network).
    Active players are then enriched with position + current team by walking
    each team's roster (one call per team). Returns a small count summary.
    """
    if sleep is None:
        import time
        sleep = time.sleep
    if players is None or teams is None or fetch_team_roster is None:
        players, teams, fetch_team_roster = _default_reference_sources(
            players, teams, fetch_team_roster
        )

    db.init_schema(con)

    team_rows = transform.normalize_teams(teams)
    db.upsert_teams(con, team_rows)
    db.upsert_players(con, transform.normalize_players(players))

    # Close the gap: players with game logs but missing from the static list.
    max_season = con.execute("SELECT MAX(season) FROM game_logs").fetchone()[0]
    added_from_logs = 0
    if max_season is not None:
        added_from_logs = db.backfill_players_from_game_logs(con, active_season=max_season)

    enriched = 0
    for abbr in team_rows["abbreviation"]:
        roster = fetch_team_roster(abbr)
        enriched += db.enrich_players(con, transform.normalize_roster(roster, abbr))
        sleep(rate_limit)

    return {
        "teams": db.count_teams(con),
        "players": db.count_players(con),
        "added_from_logs": added_from_logs,
        "enriched": enriched,
    }


def _default_reference_sources(players, teams, fetch_team_roster):
    """Lazily bind nba_api as the live source (kept out of unit tests)."""
    from nba_api.stats.static import players as static_players
    from nba_api.stats.static import teams as static_teams
    from nba_api.stats.endpoints import CommonTeamRoster

    if players is None:
        players = static_players.get_players()
    if teams is None:
        teams = static_teams.get_teams()
    if fetch_team_roster is None:
        team_id_by_abbr = {t["abbreviation"]: t["id"] for t in static_teams.get_teams()}

        def fetch_team_roster(abbr):
            return nba_source._retry(
                lambda: CommonTeamRoster(
                    team_id=team_id_by_abbr[abbr],
                    timeout=nba_source.REQUEST_TIMEOUT,
                ).get_data_frames()[0],
                attempts=5,
                base_delay=1.0,
            )

    return players, teams, fetch_team_roster


def pull_yahoo_league(con, league_key: str, *, client=None) -> dict:
    """Pull all team rosters for a Yahoo league and store them.

    `client` defaults to fbball.yahoo_client (the live OAuth client); inject a
    fake in tests. Returns a small summary including which team is mine.
    """
    if client is None:
        from fbball import yahoo_client as client

    db.init_schema(con)
    parsed = client.parse_all_rosters(client.get_all_team_rosters(league_key))
    teams_df, roster_df = transform.yahoo_rosters_to_frames(parsed, league_key)
    db.upsert_yahoo_teams(con, teams_df)
    db.upsert_yahoo_roster(con, roster_df)

    mine = teams_df[teams_df["is_my_team"]]
    my_team = mine.iloc[0]["name"] if len(mine) else None
    return {
        "teams": len(teams_df),
        "roster_spots": len(roster_df),
        "my_team": my_team,
    }


def summary(con) -> dict:
    """A small at-a-glance report: total rows, per-season counts, checkpoint."""
    db.init_schema(con)
    per_season = {
        row[0]: row[1]
        for row in con.execute(
            "SELECT season, COUNT(*) FROM game_logs GROUP BY season ORDER BY season"
        ).fetchall()
    }
    return {
        "total_rows": db.count_game_logs(con),
        "per_season": per_season,
        "checkpoint": db.get_checkpoint(con, SOURCE),
    }


def backfill(
    con,
    seasons,
    *,
    current_season: str | None = None,
    season_type: str = "Regular Season",
    fetch=nba_source.fetch_season_logs,
    sleep=None,
    rate_limit: float = nba_source.RATE_LIMIT_SECONDS,
) -> int:
    """Load each requested season once. Returns total new rows inserted.

    Resumable in any order: a season is skipped only if it's explicitly marked
    complete. A completed historical season is immutable, so once loaded it's
    never re-pulled. The `current_season` is never marked complete (more games
    are coming), so it always re-pulls — idempotent, so that's harmless.
    """
    if sleep is None:
        import time
        sleep = time.sleep

    db.init_schema(con)

    total_new = 0
    for season in sorted(seasons):
        if db.is_season_complete(con, season):
            continue
        raw = fetch(season, season_type)
        rows = transform.normalize_game_logs(raw, season_type)
        total_new += db.upsert_game_logs(con, rows)
        db.set_checkpoint(con, SOURCE, season=season, last_date=_max_date(rows))
        if season != current_season:
            db.mark_season_complete(con, season)
        sleep(rate_limit)

    return total_new


def update(
    con,
    season: str,
    *,
    season_type: str = "Regular Season",
    fetch=nba_source.fetch_season_logs,
) -> int:
    """Pull the current season and upsert. Returns count of new games added."""
    db.init_schema(con)
    raw = fetch(season, season_type)
    rows = transform.normalize_game_logs(raw, season_type)
    new = db.upsert_game_logs(con, rows)
    max_date = _max_date(rows)
    if max_date is not None:
        db.set_checkpoint(con, SOURCE, season=season, last_date=max_date)
    return new
