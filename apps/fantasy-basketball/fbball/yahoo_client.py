"""Yahoo Fantasy API client with OAuth 2.0 authentication."""

import json
import os
import time
import urllib.parse
import requests

# Yahoo OAuth 2.0 endpoints
AUTH_URL = "https://api.login.yahoo.com/oauth2/request_auth"
TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"

# Yahoo Fantasy API base
FANTASY_BASE = "https://fantasysports.yahooapis.com/fantasy/v2"

# Yahoo stat_id → display name for 9-cat H2H
STAT_ID_MAP = {
    '5': 'FG%', '8': 'FT%', '10': '3PTM', '12': 'PTS',
    '15': 'REB', '16': 'AST', '17': 'STL', '18': 'BLK', '19': 'TO',
}

# Credentials live in the project root (one level up from this package),
# gitignored so they never commit. Overridable via env vars for flexibility.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CREDS_FILE = os.environ.get(
    "YAHOO_CREDS_FILE", os.path.join(_PROJECT_ROOT, "yahoo_creds.json")
)
TOKEN_FILE = os.environ.get(
    "YAHOO_TOKEN_FILE", os.path.join(_PROJECT_ROOT, "yahoo_token.json")
)


def _load_creds() -> dict:
    """Load client_id and client_secret from yahoo_creds.json."""
    if not os.path.exists(CREDS_FILE):
        raise FileNotFoundError(f"Credentials file not found: {CREDS_FILE}")
    with open(CREDS_FILE, "r") as f:
        return json.load(f)


def _save_token(token_data: dict):
    """Persist token data to yahoo_token.json."""
    with open(TOKEN_FILE, "w") as f:
        json.dump(token_data, f, indent=2)


def _load_token() -> dict | None:
    """Load token data from yahoo_token.json, or None if missing."""
    if not os.path.exists(TOKEN_FILE):
        return None
    with open(TOKEN_FILE, "r") as f:
        return json.load(f)


def get_auth_url() -> str:
    """Build the Yahoo OAuth 2.0 authorization URL."""
    creds = _load_creds()
    redirect_uri = creds.get("redirect_uri", "oob")
    params = {
        "client_id": creds["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "language": "en-us",
    }
    return AUTH_URL + "?" + urllib.parse.urlencode(params)


def exchange_code(code: str) -> dict:
    """Exchange authorization code for access + refresh tokens."""
    creds = _load_creds()
    redirect_uri = creds.get("redirect_uri", "oob")
    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        },
        auth=(creds["client_id"], creds["client_secret"]),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=15,
    )
    resp.raise_for_status()
    token_data = resp.json()
    token_data["expires_at"] = time.time() + token_data.get("expires_in", 3600)
    _save_token(token_data)
    return token_data


def refresh_access_token() -> dict:
    """Use refresh_token to get a new access_token."""
    creds = _load_creds()
    token = _load_token()
    if not token or "refresh_token" not in token:
        raise ValueError("No refresh token available. Re-authenticate.")

    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": token["refresh_token"],
        },
        auth=(creds["client_id"], creds["client_secret"]),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=15,
    )
    resp.raise_for_status()
    new_token = resp.json()
    new_token["expires_at"] = time.time() + new_token.get("expires_in", 3600)
    # Preserve refresh_token if not returned
    if "refresh_token" not in new_token and "refresh_token" in token:
        new_token["refresh_token"] = token["refresh_token"]
    _save_token(new_token)
    return new_token


def is_authenticated() -> bool:
    """Check if we have a valid (or refreshable) token."""
    token = _load_token()
    if not token:
        return False
    return "access_token" in token and "refresh_token" in token


def _get_access_token() -> str:
    """Get a valid access token, refreshing if needed."""
    token = _load_token()
    if not token:
        raise ValueError("Not authenticated. Complete OAuth flow first.")

    # Refresh if expired or about to expire (60s buffer)
    if time.time() >= token.get("expires_at", 0) - 60:
        token = refresh_access_token()

    return token["access_token"]


def yahoo_request(endpoint: str, params: dict | None = None) -> dict:
    """Authenticated GET to Yahoo Fantasy API with auto-refresh on 401."""
    if not endpoint.startswith("http"):
        url = FANTASY_BASE + endpoint
    else:
        url = endpoint

    # Always request JSON
    if params is None:
        params = {}
    params["format"] = "json"

    access_token = _get_access_token()
    headers = {"Authorization": f"Bearer {access_token}"}

    resp = requests.get(url, headers=headers, params=params, timeout=15)

    # Auto-refresh on 401
    if resp.status_code == 401:
        access_token = refresh_access_token()["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}
        resp = requests.get(url, headers=headers, params=params, timeout=15)

    resp.raise_for_status()
    return resp.json()


# ── Fantasy API Methods ──────────────────────────────────────────────


def get_user_leagues(game_key: str = "nba") -> dict:
    """Get user's fantasy leagues for a game."""
    return yahoo_request(f"/users;use_login=1/games;game_keys={game_key}/leagues")


def get_league_info(league_key: str) -> dict:
    """Get league settings and metadata."""
    return yahoo_request(f"/league/{league_key}/settings")


def get_league_standings(league_key: str) -> dict:
    """Get league standings."""
    return yahoo_request(f"/league/{league_key}/standings")


def get_team_roster(team_key: str) -> dict:
    """Get a team's current roster."""
    return yahoo_request(f"/team/{team_key}/roster")


def get_league_scoreboard(league_key: str, week: int | None = None) -> dict:
    """Get league scoreboard (matchups)."""
    endpoint = f"/league/{league_key}/scoreboard"
    params = {}
    if week is not None:
        params["week"] = week
    return yahoo_request(endpoint, params)


def get_league_transactions(league_key: str) -> dict:
    """Get league transactions."""
    return yahoo_request(f"/league/{league_key}/transactions")


def get_league_draft_results(league_key: str) -> dict:
    """Get league draft results."""
    return yahoo_request(f"/league/{league_key}/draftresults")


# ── Response Parsing Helpers ─────────────────────────────────────────


def parse_leagues(raw: dict) -> list[dict]:
    """Extract league list from raw get_user_leagues response."""
    try:
        games = raw["fantasy_content"]["users"]["0"]["user"][1]["games"]
        leagues = []
        # games is {"0": {"game": [...]}, "count": N}
        game_count = games.get("count", 0)
        for gi in range(game_count):
            game_data = games[str(gi)]["game"]
            # game_data = [game_meta, {"leagues": {...}}]
            if len(game_data) < 2:
                continue
            league_block = game_data[1].get("leagues", {})
            league_count = league_block.get("count", 0)
            for li in range(league_count):
                league_raw = league_block[str(li)]["league"][0]
                leagues.append({
                    "league_key": league_raw.get("league_key", ""),
                    "league_id": league_raw.get("league_id", ""),
                    "name": league_raw.get("name", ""),
                    "num_teams": league_raw.get("num_teams", 0),
                    "season": league_raw.get("season", ""),
                    "scoring_type": league_raw.get("scoring_type", ""),
                    "current_week": league_raw.get("current_week", ""),
                    "url": league_raw.get("url", ""),
                })
        return leagues
    except (KeyError, IndexError, TypeError):
        return []


def _extract_managers(meta: list) -> list[dict]:
    """Extract manager info (nickname, guid, email) from team meta list."""
    managers = []
    for item in meta:
        if not isinstance(item, dict) or "managers" not in item:
            continue
        mgr_data = item["managers"]
        # Could be a list or a numbered dict
        if isinstance(mgr_data, list):
            for mg in mgr_data:
                if isinstance(mg, dict):
                    m = mg.get("manager", mg)
                    managers.append({
                        "nickname": m.get("nickname", ""),
                        "guid": m.get("guid", ""),
                        "email": m.get("email", ""),
                        "manager_id": m.get("manager_id", ""),
                        "image_url": m.get("image_url", ""),
                    })
        elif isinstance(mgr_data, dict):
            for k, v in mgr_data.items():
                if not isinstance(v, dict):
                    continue
                m = v.get("manager", v)
                if "nickname" in m or "guid" in m:
                    managers.append({
                        "nickname": m.get("nickname", ""),
                        "guid": m.get("guid", ""),
                        "email": m.get("email", ""),
                        "manager_id": m.get("manager_id", ""),
                        "image_url": m.get("image_url", ""),
                    })
    return managers


def _extract_team_stats(team_data: list) -> dict:
    """Extract 9-cat stats from team data elements, mapped by STAT_ID_MAP."""
    for elem in team_data[1:]:
        if not isinstance(elem, dict) or "team_stats" not in elem:
            continue
        stats = {}
        for s in elem["team_stats"].get("stats", []):
            if isinstance(s, dict) and "stat" in s:
                stat = s["stat"]
                sid = str(stat.get("stat_id", ""))
                if sid in STAT_ID_MAP:
                    stats[STAT_ID_MAP[sid]] = stat.get("value", "")
        return stats
    return {}


def parse_standings(raw: dict) -> list[dict]:
    """Extract standings from raw get_league_standings response.

    Handles Yahoo's variable-position structure: searches through
    team_data elements for team_standings and team_stats rather
    than assuming fixed indices.
    """
    try:
        standings_block = raw["fantasy_content"]["league"][1]["standings"][0]["teams"]
        team_count = standings_block.get("count", 0)
        teams = []
        for ti in range(team_count):
            team_data = standings_block[str(ti)]["team"]
            meta = team_data[0]
            # Extract basic team info from meta list
            info = {}
            for item in meta:
                if isinstance(item, dict) and "managers" not in item:
                    info.update(item)

            # Extract managers (with email for unique owner tracking)
            managers = _extract_managers(meta)

            # Search through remaining elements for team_standings
            standings_info = {}
            for elem in team_data[1:]:
                if isinstance(elem, dict) and "team_standings" in elem:
                    standings_info = elem["team_standings"]
                    break

            outcome = standings_info.get("outcome_totals", {})

            # Extract 9-cat stats
            cat_stats = _extract_team_stats(team_data)

            teams.append({
                "team_key": info.get("team_key", ""),
                "name": info.get("name", ""),
                "managers": managers,
                "rank": int(standings_info.get("rank", 0)),
                "playoff_seed": standings_info.get("playoff_seed", ""),
                "games_back": standings_info.get("games_back", ""),
                "wins": int(outcome.get("wins", 0)),
                "losses": int(outcome.get("losses", 0)),
                "ties": int(outcome.get("ties", 0)),
                "percentage": outcome.get("percentage", ""),
                "points_for": standings_info.get("points_for", ""),
                "points_against": standings_info.get("points_against", ""),
                "stats": cat_stats,
            })
        return teams
    except (KeyError, IndexError, TypeError):
        return []


def parse_roster(raw: dict) -> list[dict]:
    """Extract roster players from raw get_team_roster response."""
    try:
        roster_block = raw["fantasy_content"]["team"][1]["roster"]["0"]["players"]
        player_count = roster_block.get("count", 0)
        players = []
        for pi in range(player_count):
            player_data = roster_block[str(pi)]["player"]
            meta = player_data[0]
            # meta is a list of dicts
            info = {}
            for item in meta:
                if isinstance(item, dict):
                    info.update(item)
                    if "name" in item:
                        info["full_name"] = item["name"].get("full", "")

            position = ""
            if len(player_data) > 1:
                sel_pos = player_data[1].get("selected_position", [])
                if sel_pos and len(sel_pos) > 0:
                    for sp in sel_pos:
                        if isinstance(sp, dict) and "position" in sp:
                            position = sp["position"]

            players.append({
                "player_key": info.get("player_key", ""),
                "name": info.get("full_name", info.get("name", "")),
                "team": info.get("editorial_team_abbr", ""),
                "position": position,
                "eligible_positions": info.get("eligible_positions", []),
                "status": info.get("status", ""),
            })
        return players
    except (KeyError, IndexError, TypeError):
        return []


def parse_scoreboard(raw: dict) -> dict:
    """Extract matchups from raw get_league_scoreboard response."""
    try:
        sb = raw["fantasy_content"]["league"][1]["scoreboard"]
        week = sb.get("week", "")
        matchups_block = sb["0"]["matchups"]
        matchup_count = matchups_block.get("count", 0)
        matchups = []
        for mi in range(matchup_count):
            m = matchups_block[str(mi)]["matchup"]
            teams_block = m.get("0", m).get("teams", m.get("0", {}).get("teams", {}))
            if not teams_block:
                # Try alternate structure
                if isinstance(m, list):
                    teams_block = m[0].get("teams", {})
                elif isinstance(m, dict):
                    teams_block = m.get("teams", {})

            team_count = teams_block.get("count", 0) if isinstance(teams_block, dict) else 0
            matchup_teams = []
            for ti in range(team_count):
                team_data = teams_block[str(ti)]["team"]
                meta = team_data[0]
                info = {}
                for item in meta:
                    if isinstance(item, dict):
                        info.update(item)

                stats = {}
                if len(team_data) > 1:
                    team_stats = team_data[1].get("team_stats", {})
                    stat_list = team_stats.get("stats", [])
                    for s in stat_list:
                        if isinstance(s, dict) and "stat" in s:
                            stat = s["stat"]
                            stats[stat.get("stat_id", "")] = stat.get("value", "")

                matchup_teams.append({
                    "team_key": info.get("team_key", ""),
                    "name": info.get("name", ""),
                    "stats": stats,
                })

            status = m.get("status", "") if isinstance(m, dict) else ""
            matchups.append({
                "status": status,
                "teams": matchup_teams,
            })

        return {"week": week, "matchups": matchups}
    except (KeyError, IndexError, TypeError):
        return {"week": "", "matchups": []}


def parse_transactions(raw: dict) -> list[dict]:
    """Extract transactions from raw get_league_transactions response."""
    try:
        tx_block = raw["fantasy_content"]["league"][1]["transactions"]
        tx_count = tx_block.get("count", 0)
        transactions = []
        for ti in range(tx_count):
            tx = tx_block[str(ti)]["transaction"]
            tx_data = tx[0] if isinstance(tx, list) else tx
            info = {}
            if isinstance(tx_data, dict):
                info = tx_data

            players_involved = []
            if isinstance(tx, list) and len(tx) > 1:
                players_block = tx[1].get("players", {})
                p_count = players_block.get("count", 0)
                for pi in range(p_count):
                    p = players_block[str(pi)]["player"]
                    p_meta = p[0]
                    p_info = {}
                    for item in p_meta:
                        if isinstance(item, dict):
                            p_info.update(item)
                            if "name" in item:
                                p_info["full_name"] = item["name"].get("full", "")
                    tx_data_p = p[1].get("transaction_data", {}) if len(p) > 1 else {}
                    if isinstance(tx_data_p, list):
                        tx_data_p = tx_data_p[0] if tx_data_p else {}
                    players_involved.append({
                        "name": p_info.get("full_name", ""),
                        "team": p_info.get("editorial_team_abbr", ""),
                        "type": tx_data_p.get("type", ""),
                        "source_team": tx_data_p.get("source_team_name", ""),
                        "dest_team": tx_data_p.get("destination_team_name", ""),
                    })

            transactions.append({
                "transaction_key": info.get("transaction_key", ""),
                "type": info.get("type", ""),
                "status": info.get("status", ""),
                "timestamp": info.get("timestamp", ""),
                "players": players_involved,
            })
        return transactions
    except (KeyError, IndexError, TypeError):
        return []


def parse_draft_results(raw: dict) -> list[dict]:
    """Extract draft results from raw get_league_draft_results response."""
    try:
        dr_block = raw["fantasy_content"]["league"][1]["draft_results"]
        dr_count = dr_block.get("count", 0)
        results = []
        for di in range(dr_count):
            pick = dr_block[str(di)]["draft_result"]
            results.append({
                "pick": pick.get("pick", 0),
                "round": pick.get("round", 0),
                "team_key": pick.get("team_key", ""),
                "player_key": pick.get("player_key", ""),
            })
        return results
    except (KeyError, IndexError, TypeError):
        return []


# ── Additional API Methods ─────────────────────────────────────────


def get_all_team_rosters(league_key: str) -> dict:
    """Get all teams' rosters in one API call."""
    return yahoo_request(f"/league/{league_key}/teams/roster")


def get_league_player_ranks(league_key: str) -> dict:
    """Get Yahoo's current player rankings for all rostered players.

    Paginates through 25-player pages since Yahoo caps per request.
    Returns a dict: player_key -> rank AND player_name -> rank.
    """
    ranks = {}
    start = 0
    page_size = 25
    while True:
        raw = yahoo_request(
            f"/league/{league_key}/players;status=T;sort=AR",
            params={"start": start, "count": page_size},
        )
        try:
            players_block = raw["fantasy_content"]["league"][1]["players"]
            p_count = players_block.get("count", 0)
            if p_count == 0:
                break
            for pi in range(p_count):
                player_data = players_block[str(pi)]["player"]
                meta = player_data[0]
                info = {}
                name_full = ""
                for item in meta:
                    if isinstance(item, dict):
                        if "name" in item:
                            name_full = item["name"].get("full", "")
                        else:
                            info.update(item)
                pk = info.get("player_key", "")
                rank = start + pi + 1  # position in AR-sorted list = rank
                if pk:
                    ranks[pk] = rank
                if name_full:
                    ranks[name_full] = rank
            start += p_count
            if p_count < page_size:
                break  # last page
        except (KeyError, IndexError, TypeError):
            break
    return ranks


def get_free_agents(league_key: str, limit: int = 200) -> list[dict]:
    """Fetch available (free-agent + waiver) players, best first.

    Paginates /players;status=A;sort=AR in 25s. Returns dicts with player_key,
    name, team, eligible_positions, status.
    """
    out = []
    start = 0
    page = 25
    while len(out) < limit:
        raw = yahoo_request(
            f"/league/{league_key}/players;status=A;sort=AR",
            params={"start": start, "count": page},
        )
        try:
            block = raw["fantasy_content"]["league"][1]["players"]
            count = block.get("count", 0)
        except (KeyError, IndexError, TypeError):
            break
        if count == 0:
            break
        for pi in range(count):
            entry = block.get(str(pi))
            if not entry or "player" not in entry:
                continue
            meta = entry["player"][0]
            info = {}
            name = ""
            for item in meta:
                if isinstance(item, dict):
                    if "name" in item:
                        name = item["name"].get("full", "")
                    else:
                        info.update(item)
            out.append({
                "player_key": info.get("player_key", ""),
                "name": name,
                "team": info.get("editorial_team_abbr", ""),
                "eligible_positions": _eligible_position_strings(
                    info.get("eligible_positions", [])
                ),
                "status": info.get("status", ""),
            })
        start += count
        if count < page:
            break
    return out[:limit]


def get_player_names(league_key: str, player_keys: list[str], batch: int = 25) -> dict:
    """Resolve player_key -> full name, batching (Yahoo caps keys per request).

    Used to name drafted-then-dropped players who aren't on any final roster.
    """
    out = {}
    keys = [k for k in player_keys if k]
    for i in range(0, len(keys), batch):
        chunk = keys[i:i + batch]
        raw = yahoo_request(
            f"/league/{league_key}/players;player_keys={','.join(chunk)}"
        )
        try:
            block = raw["fantasy_content"]["league"][1]["players"]
            count = block.get("count", 0)
        except (KeyError, IndexError, TypeError):
            continue
        for pi in range(count):
            entry = block.get(str(pi))
            if not entry or "player" not in entry:
                continue
            meta = entry["player"][0]
            info, name = {}, ""
            for item in meta:
                if isinstance(item, dict):
                    if "name" in item:
                        name = item["name"].get("full", "")
                    else:
                        info.update(item)
            pk = info.get("player_key", "")
            if pk:
                out[pk] = name
    return out


def get_league_metadata(league_key: str) -> dict:
    """Get league metadata including renew field for history chain."""
    return yahoo_request(f"/league/{league_key}/metadata")


def parse_league_meta(raw: dict) -> dict:
    """Extract league metadata from raw response."""
    try:
        league_data = raw["fantasy_content"]["league"][0]
        if isinstance(league_data, list):
            info = {}
            for item in league_data:
                if isinstance(item, dict):
                    info.update(item)
            return info
        return league_data if isinstance(league_data, dict) else {}
    except (KeyError, IndexError, TypeError):
        return {}


def _eligible_position_strings(elig) -> list[str]:
    """Yahoo eligible_positions -> flat list of position strings.

    Raw is usually [{"position": "PG"}, {"position": "SG"}, ...]; tolerate
    plain strings too. Drops the synthetic IL/IL+ slots (not real eligibility).
    """
    out = []
    for e in elig or []:
        if isinstance(e, dict) and "position" in e:
            out.append(e["position"])
        elif isinstance(e, str):
            out.append(e)
    return [p for p in out if p not in ("IL", "IL+")]


def parse_all_rosters(raw: dict) -> list[dict]:
    """Extract rosters for all teams from /league/{key}/teams/roster response."""
    try:
        teams_block = raw["fantasy_content"]["league"][1]["teams"]
        team_count = teams_block.get("count", 0)
        all_teams = []
        for ti in range(team_count):
            team_data = teams_block[str(ti)]["team"]
            meta = team_data[0]
            info = {}
            for item in meta:
                if isinstance(item, dict) and "managers" not in item:
                    info.update(item)
            managers = _extract_managers(meta)

            # Find the roster in the team data
            players = []
            for elem in team_data[1:]:
                if not isinstance(elem, dict) or "roster" not in elem:
                    continue
                roster = elem["roster"]
                # roster is {"0": {"players": {...}}, "coverage_type": ...}
                players_block = None
                for rk, rv in roster.items():
                    if isinstance(rv, dict) and "players" in rv:
                        players_block = rv["players"]
                        break
                if not players_block:
                    # Try direct players key
                    players_block = roster.get("players", {})
                if not players_block:
                    continue

                p_count = players_block.get("count", 0)
                for pi in range(p_count):
                    p_entry = players_block.get(str(pi))
                    if not p_entry or "player" not in p_entry:
                        continue
                    player_data = p_entry["player"]
                    p_meta = player_data[0]
                    p_info = {}
                    for item in p_meta:
                        if isinstance(item, dict):
                            p_info.update(item)
                            if "name" in item:
                                p_info["full_name"] = item["name"].get("full", "")

                    position = ""
                    if len(player_data) > 1:
                        sel_pos = player_data[1].get("selected_position", [])
                        if sel_pos:
                            for sp in sel_pos:
                                if isinstance(sp, dict) and "position" in sp:
                                    position = sp["position"]

                    players.append({
                        "player_key": p_info.get("player_key", ""),
                        "name": p_info.get("full_name", p_info.get("name", "")),
                        "team": p_info.get("editorial_team_abbr", ""),
                        "position": position,
                        "eligible_positions": _eligible_position_strings(
                            p_info.get("eligible_positions", [])
                        ),
                        "status": p_info.get("status", ""),
                    })

            all_teams.append({
                "team_key": info.get("team_key", ""),
                "name": info.get("name", ""),
                "managers": managers,
                "is_my_team": str(info.get("is_owned_by_current_login", "0")) == "1",
                "players": players,
            })
        return all_teams
    except (KeyError, IndexError, TypeError):
        return []


def parse_scoreboard_cats(raw: dict) -> dict:
    """Extract matchups with named category stats from scoreboard response."""
    try:
        sb = raw["fantasy_content"]["league"][1]["scoreboard"]
        week = sb.get("week", "")
        matchups_block = sb["0"]["matchups"]
        matchup_count = matchups_block.get("count", 0)
        matchups = []
        for mi in range(matchup_count):
            m = matchups_block[str(mi)]["matchup"]

            # Extract status and winner_team_key
            m_meta = m if isinstance(m, dict) else {}
            if isinstance(m, list):
                m_meta = m[0] if m else {}
            status = m_meta.get("status", "")
            is_tied = m_meta.get("is_tied", 0)

            # Find teams block
            teams_block = m_meta.get("0", m_meta).get("teams", {})
            if not teams_block and isinstance(m_meta, dict):
                teams_block = m_meta.get("teams", {})

            team_count = teams_block.get("count", 0) if isinstance(teams_block, dict) else 0
            matchup_teams = []
            for ti in range(team_count):
                team_data = teams_block[str(ti)]["team"]
                meta = team_data[0]
                info = {}
                for item in meta:
                    if isinstance(item, dict):
                        info.update(item)
                managers = _extract_managers(meta)

                # Extract stats with named categories
                cat_stats = _extract_team_stats(team_data)

                # Also get win/loss/tie for this matchup
                team_points = {}
                for elem in team_data[1:]:
                    if isinstance(elem, dict) and "team_points" in elem:
                        team_points = elem["team_points"]

                matchup_teams.append({
                    "team_key": info.get("team_key", ""),
                    "name": info.get("name", ""),
                    "managers": managers,
                    "stats": cat_stats,
                    "points": team_points.get("total", ""),
                    "win_probability": info.get("win_probability", ""),
                })

            matchups.append({
                "status": status,
                "is_tied": is_tied,
                "teams": matchup_teams,
            })

        return {"week": week, "matchups": matchups}
    except (KeyError, IndexError, TypeError):
        return {"week": "", "matchups": []}
