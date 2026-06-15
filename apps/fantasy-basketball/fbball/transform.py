"""Pure transforms: raw nba_api frames -> our storage schema.

No network, no DB — just column mapping so it's trivially testable and
swappable if the upstream API shape ever shifts.
"""

import pandas as pd

from fbball.db import GAME_LOG_COLUMNS

# raw nba_api PlayerGameLogs column  ->  our schema column
_RAW_TO_SCHEMA = {
    "PLAYER_ID": "player_id",
    "PLAYER_NAME": "player_name",
    "TEAM_ABBREVIATION": "team",
    "SEASON_YEAR": "season",
    "GAME_ID": "game_id",
    "GAME_DATE": "game_date",
    "MIN": "min",
    "FGM": "fgm", "FGA": "fga",
    "FTM": "ftm", "FTA": "fta",
    "FG3M": "fg3m",
    "PTS": "pts", "REB": "reb", "AST": "ast",
    "STL": "stl", "BLK": "blk", "TOV": "tov",
}


def normalize_game_logs(raw: pd.DataFrame, season_type: str) -> pd.DataFrame:
    """Map a raw PlayerGameLogs frame to GAME_LOG_COLUMNS order.

    `season_type` is injected (the bulk endpoint doesn't echo it back).
    Extra upstream columns are dropped; game_date is parsed to a date.
    """
    out = pd.DataFrame()
    for raw_col, schema_col in _RAW_TO_SCHEMA.items():
        out[schema_col] = raw[raw_col] if raw_col in raw.columns else None

    out["season_type"] = season_type
    out["game_date"] = pd.to_datetime(out["game_date"]).dt.date

    return out[GAME_LOG_COLUMNS]


def normalize_bios(raw: pd.DataFrame, season: str) -> pd.DataFrame:
    """LeagueDashPlayerBioStats frame -> player_bio rows (season, player_id, age)."""
    out = pd.DataFrame()
    out["season"] = season
    out["player_id"] = raw["PLAYER_ID"] if "PLAYER_ID" in raw.columns else None
    out["age"] = raw["AGE"] if "AGE" in raw.columns else None
    if len(raw):
        out["season"] = season
    return out[["season", "player_id", "age"]]


def normalize_teams(static_teams: list) -> pd.DataFrame:
    """nba_api.stats.static.teams.get_teams() list -> teams rows."""
    return pd.DataFrame(
        [
            {
                "team_id": t["id"],
                "abbreviation": t["abbreviation"],
                "full_name": t["full_name"],
                "city": t.get("city"),
                "nickname": t.get("nickname"),
            }
            for t in static_teams
        ],
        columns=["team_id", "abbreviation", "full_name", "city", "nickname"],
    )


def normalize_players(static_players: list) -> pd.DataFrame:
    """nba_api.stats.static.players.get_players() list -> players identity rows."""
    return pd.DataFrame(
        [
            {
                "player_id": p["id"],
                "full_name": p["full_name"],
                "is_active": bool(p["is_active"]),
            }
            for p in static_players
        ],
        columns=["player_id", "full_name", "is_active"],
    )


def yahoo_rosters_to_frames(parsed_teams: list, league_key: str):
    """parse_all_rosters() output -> (teams_df, roster_df) ready for storage.

    eligible_positions (a list) is flattened to a comma string; nba_player_id
    starts NULL and is filled later by the name-matching bridge.
    """
    team_records, roster_records = [], []
    for t in parsed_teams:
        mgr = t["managers"][0]["nickname"] if t.get("managers") else ""
        team_records.append({
            "team_key": t["team_key"],
            "league_key": league_key,
            "name": t["name"],
            "manager": mgr,
            "is_my_team": bool(t.get("is_my_team", False)),
        })
        for p in t.get("players", []):
            elig = p.get("eligible_positions", [])
            if isinstance(elig, list):
                elig = ",".join(str(e) for e in elig)
            roster_records.append({
                "team_key": t["team_key"],
                "player_key": p.get("player_key", ""),
                "player_name": p.get("name", ""),
                "editorial_team": p.get("team", ""),
                "selected_position": p.get("position", ""),
                "eligible_positions": elig,
                "status": p.get("status", ""),
                "nba_player_id": None,
            })

    teams_df = pd.DataFrame(
        team_records,
        columns=["team_key", "league_key", "name", "manager", "is_my_team"],
    )
    roster_df = pd.DataFrame(
        roster_records,
        columns=["team_key", "player_key", "player_name", "editorial_team",
                 "selected_position", "eligible_positions", "status", "nba_player_id"],
    )
    return teams_df, roster_df


def free_agents_to_frame(parsed_fas: list, league_key: str) -> pd.DataFrame:
    """get_free_agents() output -> yahoo_free_agents rows."""
    records = []
    for p in parsed_fas:
        elig = p.get("eligible_positions", [])
        if isinstance(elig, list):
            elig = ",".join(str(e) for e in elig)
        records.append({
            "league_key": league_key,
            "player_key": p.get("player_key", ""),
            "player_name": p.get("name", ""),
            "editorial_team": p.get("team", ""),
            "eligible_positions": elig,
            "status": p.get("status", ""),
            "nba_player_id": None,
        })
    return pd.DataFrame(
        records,
        columns=["league_key", "player_key", "player_name", "editorial_team",
                 "eligible_positions", "status", "nba_player_id"],
    )


def normalize_roster(roster: pd.DataFrame, team: str) -> pd.DataFrame:
    """A CommonTeamRoster frame -> player_id/nba_position/team rows."""
    out = pd.DataFrame()
    out["player_id"] = roster["PLAYER_ID"] if "PLAYER_ID" in roster.columns else None
    out["nba_position"] = roster["POSITION"] if "POSITION" in roster.columns else None
    out["team"] = team
    return out[["player_id", "nba_position", "team"]]
