"""Yahoo league HISTORY — a fixed, immutable data lake of every past season.

The league renews each year under a new league_key; we walk the "renew" chain
back to 2010 and capture, per season: teams + owners (keyed by email, since
owners change), draft results, final rosters, and standings.

Standings carry two distinct orderings (the important subtlety):
  - final_rank   — reflects the PLAYOFFS (the championship result)
  - playoff_seed — the regular-season seed (playoff teams only)
We also derive regular_season_rank for ALL teams from their W-L record, so the
full regular-season order is recoverable even for non-playoff teams.
"""


def _to_float(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _to_int(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def derive_regular_season_ranks(teams: list[dict]) -> list[dict]:
    """Order teams by regular-season strength and assign regular_season_rank.

    Tiebreak: wins, then win%, then points_for — all descending.
    """
    ordered = sorted(
        teams,
        key=lambda t: (t.get("wins", 0), _to_float(t.get("win_pct")),
                       _to_float(t.get("points_for"))),
        reverse=True,
    )
    out = []
    for i, t in enumerate(ordered, 1):
        r = dict(t)
        r["regular_season_rank"] = i
        out.append(r)
    return out


def season_row(meta: dict, season: int, league_key: str) -> dict:
    return {
        "season": season,
        "league_key": league_key,
        "name": meta.get("name"),
        "num_teams": _to_int(meta.get("num_teams")),
        "start_date": meta.get("start_date") or None,
        "end_date": meta.get("end_date") or None,
    }


def teams_rows(parsed_standings: list[dict], season: int) -> list[dict]:
    """Teams + owner identity from a parsed standings response."""
    rows = []
    for t in parsed_standings:
        mgr = t["managers"][0] if t.get("managers") else {}
        rows.append({
            "season": season,
            "team_key": t["team_key"],
            "team_name": t.get("name", ""),
            "manager_nickname": mgr.get("nickname", ""),
            "manager_email": mgr.get("email", ""),
            "manager_guid": mgr.get("guid", ""),
        })
    return rows


def standings_rows(parsed_standings: list[dict], season: int) -> list[dict]:
    """Standings rows with final_rank, playoff_seed, and derived
    regular_season_rank (for all teams)."""
    base = []
    for t in parsed_standings:
        base.append({
            "season": season,
            "team_key": t["team_key"],
            "final_rank": _to_int(t.get("rank")),
            "playoff_seed": _to_int(t.get("playoff_seed")),
            "wins": int(t.get("wins", 0)),
            "losses": int(t.get("losses", 0)),
            "ties": int(t.get("ties", 0)),
            "win_pct": _to_float(t.get("percentage")),
            "games_back": str(t.get("games_back", "")),
            "points_for": str(t.get("points_for", "")),
        })
    return derive_regular_season_ranks(base)


def draft_rows(parsed_draft: list[dict], season: int, name_map: dict) -> list[dict]:
    """Draft picks with player names resolved via name_map (NULL if unknown)."""
    rows = []
    for d in parsed_draft:
        rows.append({
            "season": season,
            "pick": _to_int(d.get("pick")),
            "round": _to_int(d.get("round")),
            "team_key": d.get("team_key", ""),
            "player_key": d.get("player_key", ""),
            "player_name": name_map.get(d.get("player_key", "")),
        })
    return rows


def final_roster_rows(parsed_rosters: list[dict], season: int) -> list[dict]:
    """End-of-season rosters (for a completed season the current roster IS final)."""
    rows = []
    for t in parsed_rosters:
        for p in t.get("players", []):
            elig = p.get("eligible_positions", [])
            if isinstance(elig, list):
                elig = ",".join(str(e) for e in elig)
            rows.append({
                "season": season,
                "team_key": t["team_key"],
                "player_key": p.get("player_key", ""),
                "player_name": p.get("name", ""),
                "eligible_positions": elig,
                "status": p.get("status", ""),
            })
    return rows


def _slug(text: str) -> str:
    return "".join(c for c in (text or "").lower() if c.isalnum()) or "owner"


def reconcile_owners(team_rows: list[dict]) -> list[dict]:
    """Resolve true owner identity across seasons, prioritizing TEAM-NAME
    continuity but also bridging via email and nickname.

    Two team-seasons are the same owner if they share any NON-BLANK signal
    (team_name, manager_email, or manager_nickname). This survives both an
    email going blank/changing (linked by name) and a team rename (linked by
    email/nickname). Returns each team-season tagged with owner_id + owner_label
    (the owner's most-used team name).
    """
    nodes = [(r["season"], r["team_key"]) for r in team_rows]
    parent = {n: n for n in nodes}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    # Link team-seasons that share a non-blank signal.
    for field in ("team_name", "manager_email", "manager_nickname"):
        groups = {}
        for r in team_rows:
            val = (r.get(field) or "").strip().lower()
            if val:
                groups.setdefault(val, []).append((r["season"], r["team_key"]))
        for members in groups.values():
            for m in members[1:]:
                union(members[0], m)

    # Cluster, then label each owner by their most-used team name.
    from collections import Counter
    clusters = {}
    by_node = {(r["season"], r["team_key"]): r for r in team_rows}
    for n in nodes:
        clusters.setdefault(find(n), []).append(n)

    label_of = {}
    for root, members in clusters.items():
        names = Counter((by_node[m].get("team_name") or "").strip()
                        for m in members if (by_node[m].get("team_name") or "").strip())
        label = names.most_common(1)[0][0] if names else "(unknown)"
        label_of[root] = label

    out = []
    for r in team_rows:
        root = find((r["season"], r["team_key"]))
        label = label_of[root]
        out.append({
            "season": r["season"],
            "team_key": r["team_key"],
            "owner_id": _slug(label),
            "owner_label": label,
        })
    return out


def _name_map_from_rosters(parsed_rosters: list[dict]) -> dict:
    """player_key -> name, from final rosters (resolves most draft picks)."""
    m = {}
    for t in parsed_rosters:
        for p in t.get("players", []):
            if p.get("player_key"):
                m[p["player_key"]] = p.get("name", "")
    return m


def pull_league_history(con, *, client=None, start_key: str, log=None) -> dict:
    """Walk the renew chain and store every past season into the history lake."""
    import pandas as pd
    from fbball import db

    if client is None:
        from fbball import yahoo_client as client
    if log is None:
        def log(_):
            return None

    db.init_schema(con)
    chain = walk_renew_chain(client, start_key)

    totals = {"seasons": 0, "teams": 0, "standings": 0, "draft": 0, "roster": 0}
    for entry in chain:
        season, lk, meta = entry["season"], entry["league_key"], entry["meta"]
        log(f"  {season} ({lk})")

        parsed_standings = client.parse_standings(client.get_league_standings(lk))
        rosters = client.parse_all_rosters(client.get_all_team_rosters(lk))
        draft = client.parse_draft_results(client.get_league_draft_results(lk))

        # Names: final rosters cover most picks; resolve the rest (drafted then
        # dropped before season end) with a batched Yahoo player lookup.
        name_map = _name_map_from_rosters(rosters)
        missing = sorted({d.get("player_key") for d in draft
                          if d.get("player_key") and d["player_key"] not in name_map})
        if missing:
            name_map.update(client.get_player_names(lk, missing))

        db.replace_history(con, "yh_seasons",
                           pd.DataFrame([season_row(meta, season, lk)]))
        db.replace_history(con, "yh_teams",
                           pd.DataFrame(teams_rows(parsed_standings, season)))
        db.replace_history(con, "yh_standings",
                           pd.DataFrame(standings_rows(parsed_standings, season)))
        db.replace_history(con, "yh_draft",
                           pd.DataFrame(draft_rows(draft, season, name_map)))
        db.replace_history(con, "yh_final_roster",
                           pd.DataFrame(final_roster_rows(rosters, season)))

        totals["seasons"] += 1
        totals["teams"] += len(parsed_standings)
        totals["standings"] += len(parsed_standings)
        totals["draft"] += len(draft)
        totals["roster"] += sum(len(t.get("players", [])) for t in rosters)

    # Canonical owner identity across the whole history (after all seasons land).
    totals["owners"] = len({o["owner_id"] for o in
                            reconcile_owners(con.execute(
                                "SELECT season, team_key, team_name, manager_email, "
                                "manager_nickname FROM yh_teams").df().to_dict("records"))})
    rebuild_owner_identity(con)
    return totals


def rebuild_owner_identity(con) -> int:
    """Recompute canonical owner identity from yh_teams and persist it."""
    import pandas as pd
    from fbball import db

    db.init_schema(con)
    team_rows = con.execute(
        "SELECT season, team_key, team_name, manager_email, manager_nickname FROM yh_teams"
    ).df().to_dict("records")
    if not team_rows:
        return 0
    owners = reconcile_owners(team_rows)
    return db.write_owner_identity(con, pd.DataFrame(owners))


def walk_renew_chain(client, start_key: str, max_seasons: int = 25) -> list[dict]:
    """Follow the renew chain back, returning [{season, league_key, meta}, ...]."""
    out = []
    key = start_key
    for _ in range(max_seasons):
        meta = client.parse_league_meta(client.get_league_metadata(key))
        season = _to_int(meta.get("season"))
        out.append({"season": season, "league_key": key, "meta": meta})
        renew = meta.get("renew")
        if not renew or "_" not in str(renew):
            break
        gk, lid = str(renew).split("_")
        key = f"{gk}.l.{lid}"
    return out
