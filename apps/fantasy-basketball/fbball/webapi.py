"""JSON API logic for the web UI — thin functions over the data lake that take
a DuckDB connection and return JSON-able dicts. The Flask app (app.py) is a
thin wrapper that opens a read-only connection and calls these.

Kept separate from Flask so the logic is unit-testable without a server.
"""


from fbball import db, draft as draftmod, ingest, recommend, valuation

# Per-season columns surfaced for the player table + accordion.
_PLAYER_COLS = ["season", "season_type", "gp", "mpg", "ppg", "rpg", "apg", "spg",
                "bpg", "topg", "tpm_pg", "fg_pct", "ft_pct"]


def _scalar(con, sql):
    return con.execute(sql).fetchone()[0]


def _round(v, n=2):
    return round(v, n) if isinstance(v, (int, float)) else v


def players(con, search: str = "", season: str | None = None) -> list[dict]:
    """Player table for one season (default latest): one row per player."""
    season = season or db.latest_season(con)
    sql = (
        "SELECT player_id, full_name, nba_position, team, " + ", ".join(_PLAYER_COLS) + " "
        "FROM player_season_stats "
        "WHERE season = ? AND season_type = 'Regular Season'"
    )
    params = [season]
    if search:
        # accent-insensitive: "jokic" finds "Jokić"
        sql += " AND lower(strip_accents(full_name)) LIKE lower(strip_accents(?))"
        params.append(f"%{search}%")
    sql += " ORDER BY ppg DESC NULLS LAST"
    rows = con.execute(sql, params).df().to_dict("records")
    for r in rows:
        for k, v in list(r.items()):
            r[k] = _round(v) if isinstance(v, float) else v
    return rows


def player_seasons(con, player_id: int) -> list[dict]:
    """All of one player's seasons (newest first) — for the accordion."""
    rows = con.execute(
        "SELECT " + ", ".join(_PLAYER_COLS) + ", full_name, nba_position, team "
        "FROM player_season_stats WHERE player_id = ? AND season_type = 'Regular Season' "
        "ORDER BY season DESC",
        [player_id],
    ).df().to_dict("records")
    for r in rows:
        for k, v in list(r.items()):
            r[k] = _round(v) if isinstance(v, float) else v
    return rows


def rankings(con, *, source="season", punt=None, pos=None,
             min_gp=20, min_min=10.0) -> list[dict]:
    """9-cat z-score rankings (optionally projected/recent, punt-aware)."""
    ranked = valuation.rank_from_db(
        con, source=source, punt=set(punt or []), min_gp=min_gp, min_min=min_min)
    if pos:
        ranked = [r for r in ranked
                  if draftmod.primary_position(r.get("nba_position")) == pos]
        for i, r in enumerate(ranked, 1):
            r["rank"] = i
    return ranked


def draft_board(con, *, source="projection", punt=None, pos=None, gap=0.75,
                min_gp=25, min_min=15.0) -> list[dict]:
    """Tiered, positional draft board (defaults to projected value)."""
    board = draftmod.build_board(
        con, source=source, punt=set(punt or []), gap=gap,
        min_gp=min_gp, min_min=min_min)
    if pos:
        board = [r for r in board
                 if draftmod.primary_position(r.get("nba_position")) == pos]
    return board


def draft_recommend(con, *, drafted_ids, my_ids, source="projection", punt=None,
                    min_gp=25, min_min=15.0, top=40) -> dict:
    """Given the picks so far, return best-available by value and by my needs."""
    ranked = valuation.rank_from_db(
        con, source=source, punt=set(punt or []), min_gp=min_gp, min_min=min_min)
    drafted, mine = set(drafted_ids or []), set(my_ids or [])
    by_id = {r["player_id"]: r for r in ranked}

    available = [r for r in ranked if r["player_id"] not in drafted]
    profile = recommend.category_profile([by_id[i] for i in mine if i in by_id])
    weights = recommend.needs_weights(profile, set(punt or []))
    by_need = recommend.rank_waivers(available, weights)
    return {
        "available": available[:top],
        "by_need": by_need[:top],
        "profile": profile,
    }


# ── Update / refresh state ───────────────────────────────────────────────

def update_state(con) -> dict:
    """Current data state + the selectable refresh steps, for the Update tab."""
    last = con.execute("SELECT MAX(updated_at) FROM ingest_state").fetchone()[0]
    return {
        "latest_season": db.latest_season(con),
        "game_log_rows": _scalar(con, "SELECT COUNT(*) FROM game_logs"),
        "seasons": _scalar(con, "SELECT COUNT(DISTINCT season) FROM game_logs"),
        "history_seasons": _scalar(con, "SELECT COUNT(*) FROM yh_seasons"),
        "last_updated": str(last) if last else None,
        "steps": [{"key": k, "label": ingest.REFRESH_LABELS[k]}
                  for k in ingest.REFRESH_STEPS],
    }


# ── League (live rosters + 16-year history) ──────────────────────────────

def league_rosters(con) -> list[dict]:
    """Current live rosters, your team first."""
    teams = con.execute(
        "SELECT team_key, name, manager, is_my_team FROM yahoo_teams "
        "ORDER BY is_my_team DESC, name"
    ).df().to_dict("records")
    for t in teams:
        t["players"] = con.execute(
            "SELECT player_name, editorial_team, eligible_positions, status, nba_player_id "
            "FROM yahoo_roster WHERE team_key = ? ORDER BY player_name",
            [t["team_key"]],
        ).df().to_dict("records")
    return teams


def league_seasons(con) -> list[int]:
    return [r[0] for r in con.execute(
        "SELECT season FROM yh_seasons ORDER BY season DESC").fetchall()]


def league_standings(con, season: int | None = None) -> dict:
    """Standings for one history season: regular-season order + final rank."""
    if season is None:
        season = con.execute("SELECT MAX(season) FROM yh_seasons").fetchone()[0]
    rows = con.execute(
        """
        SELECT s.regular_season_rank, s.playoff_seed, s.final_rank,
               t.team_name, o.owner_label, s.wins, s.losses, s.ties
        FROM yh_standings s
        JOIN yh_teams t USING (season, team_key)
        LEFT JOIN yh_owner_identity o USING (season, team_key)
        WHERE s.season = ?
        ORDER BY s.regular_season_rank
        """,
        [season],
    ).df().to_dict("records")
    return {"season": season, "teams": rows}


def league_champions(con) -> list[dict]:
    """Champion (final_rank=1) per season, newest first."""
    return con.execute(
        """
        SELECT s.season, t.team_name, o.owner_label, s.playoff_seed, s.regular_season_rank
        FROM yh_standings s
        JOIN yh_teams t USING (season, team_key)
        LEFT JOIN yh_owner_identity o USING (season, team_key)
        WHERE s.final_rank = 1
        ORDER BY s.season DESC
        """
    ).df().to_dict("records")


def league_owners(con) -> list[dict]:
    """Canonical owners: seasons played, titles, best finish."""
    return con.execute(
        """
        SELECT o.owner_label,
               COUNT(DISTINCT o.season) AS seasons,
               MIN(o.season) AS first_season,
               MAX(o.season) AS last_season,
               SUM(CASE WHEN s.final_rank = 1 THEN 1 ELSE 0 END) AS titles,
               MIN(s.final_rank) AS best_finish
        FROM yh_owner_identity o
        JOIN yh_standings s USING (season, team_key)
        GROUP BY o.owner_label
        ORDER BY titles DESC, seasons DESC
        """
    ).df().to_dict("records")


def league_draft(con, season: int | None = None) -> dict:
    if season is None:
        season = con.execute("SELECT MAX(season) FROM yh_seasons").fetchone()[0]
    picks = con.execute(
        """
        SELECT d.pick, d.round, d.player_name, t.team_name, o.owner_label
        FROM yh_draft d
        LEFT JOIN yh_teams t USING (season, team_key)
        LEFT JOIN yh_owner_identity o USING (season, team_key)
        WHERE d.season = ? ORDER BY d.pick
        """,
        [season],
    ).df().to_dict("records")
    return {"season": season, "picks": picks}


def overview(con) -> dict:
    """Home dashboard: lake summary, your team, league quick facts."""
    rows, seasons, players_with_logs = con.execute(
        "SELECT COUNT(*), COUNT(DISTINCT season), COUNT(DISTINCT player_id) FROM game_logs"
    ).fetchone()
    smin, smax = con.execute("SELECT MIN(season), MAX(season) FROM game_logs").fetchone()

    my_team = None
    mt = con.execute("SELECT name FROM yahoo_teams WHERE is_my_team LIMIT 1").fetchone()
    if mt:
        size = _scalar(
            con,
            "SELECT COUNT(*) FROM yahoo_roster r JOIN yahoo_teams t USING (team_key) "
            "WHERE t.is_my_team",
        )
        my_team = {"name": mt[0], "roster_size": size}

    return {
        "lake": {
            "game_log_rows": rows,
            "seasons": seasons,
            "season_range": [smin, smax] if smin else None,
            "players": _scalar(con, "SELECT COUNT(*) FROM players"),
            "players_with_logs": players_with_logs,
            "teams": _scalar(con, "SELECT COUNT(*) FROM teams"),
        },
        "my_team": my_team,
        "league": {
            "history_seasons": _scalar(con, "SELECT COUNT(*) FROM yh_seasons"),
            "owners": _scalar(con, "SELECT COUNT(DISTINCT owner_id) FROM yh_owner_identity"),
        },
    }
