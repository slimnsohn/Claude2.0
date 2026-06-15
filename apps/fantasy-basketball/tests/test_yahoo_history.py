import duckdb

from fbball import db, yahoo_history as yh


def test_regular_season_ranks_order_by_record():
    teams = [
        {"team_key": "a", "wins": 80, "win_pct": 0.50, "points_for": 100},
        {"team_key": "b", "wins": 90, "win_pct": 0.55, "points_for": 110},
        {"team_key": "c", "wins": 80, "win_pct": 0.50, "points_for": 120},
    ]
    out = {r["team_key"]: r["regular_season_rank"] for r in yh.derive_regular_season_ranks(teams)}
    # b best record; a & c tie on wins+pct, c wins the points_for tiebreak
    assert out == {"b": 1, "c": 2, "a": 3}


def test_regular_season_ranks_are_sequential():
    teams = [
        {"team_key": "x", "wins": 50, "win_pct": 0.4, "points_for": 90},
        {"team_key": "y", "wins": 60, "win_pct": 0.5, "points_for": 95},
    ]
    ranks = sorted(r["regular_season_rank"] for r in yh.derive_regular_season_ranks(teams))
    assert ranks == [1, 2]


def test_standings_rows_separate_final_rank_from_seed():
    """Final rank reflects playoffs; playoff_seed is the regular-season seed."""
    parsed = [
        {"team_key": "t1", "rank": 1, "playoff_seed": "5",
         "wins": 89, "losses": 77, "ties": 5, "percentage": ".535",
         "games_back": "11.5", "points_for": "900"},
        {"team_key": "t2", "rank": 2, "playoff_seed": "1",
         "wins": 95, "losses": 70, "ties": 6, "percentage": ".574",
         "games_back": "-", "points_for": "950"},
    ]
    rows = {r["team_key"]: r for r in yh.standings_rows(parsed, season=2024)}
    champ = rows["t1"]
    assert champ["final_rank"] == 1          # won the title
    assert champ["playoff_seed"] == 5        # as a 5-seed
    assert champ["regular_season_rank"] == 2  # 2nd-best regular-season record
    assert rows["t2"]["regular_season_rank"] == 1   # best record, didn't win it all
    assert champ["season"] == 2024


def test_draft_rows_resolve_names_from_map():
    parsed = [
        {"pick": 1, "round": 1, "team_key": "t10", "player_key": "454.p.6355"},
        {"pick": 2, "round": 1, "team_key": "t4", "player_key": "454.p.9999"},
    ]
    name_map = {"454.p.6355": "Nikola Jokic"}   # 9999 not resolvable -> NULL
    rows = {r["pick"]: r for r in yh.draft_rows(parsed, season=2024, name_map=name_map)}
    assert rows[1]["player_name"] == "Nikola Jokic"
    assert rows[2]["player_name"] is None
    assert rows[1]["season"] == 2024


def _team(season, tk, name, email="", nick=""):
    return {"season": season, "team_key": tk, "team_name": name,
            "manager_email": email, "manager_nickname": nick}


def test_reconcile_owners_links_by_team_name_across_email_change():
    rows = [
        _team(2014, "t1", "LetsBall", "a@x.com", "gar"),
        _team(2015, "t2", "LetsBall", "", "gar"),        # blank email
        _team(2016, "t3", "LetsBall", "b@x.com", "gar"),  # different email
    ]
    out = {r["team_key"]: r for r in yh.reconcile_owners(rows)}
    ids = {out[t]["owner_id"] for t in ("t1", "t2", "t3")}
    assert len(ids) == 1                       # one owner across the email change
    assert out["t1"]["owner_label"] == "LetsBall"


def test_reconcile_owners_links_by_email_across_name_change():
    rows = [
        _team(2014, "t1", "Foo", "same@x.com", "n1"),
        _team(2015, "t2", "Bar", "same@x.com", "n2"),
    ]
    out = {r["team_key"]: r["owner_id"] for r in yh.reconcile_owners(rows)}
    assert out["t1"] == out["t2"]              # same email -> same owner


def test_reconcile_owners_blank_signals_do_not_link():
    rows = [
        _team(2014, "t1", "Foo", "", ""),
        _team(2015, "t2", "Bar", "", ""),
    ]
    out = {r["team_key"]: r["owner_id"] for r in yh.reconcile_owners(rows)}
    assert out["t1"] != out["t2"]              # nothing shared -> distinct owners


def test_reconcile_owner_label_is_most_common_team_name():
    rows = [
        _team(2014, "t1", "LetsBall", "a@x.com"),
        _team(2015, "t2", "LetsBall", "a@x.com"),
        _team(2013, "t0", "OldName", "a@x.com"),
    ]
    labels = {r["owner_label"] for r in yh.reconcile_owners(rows)}
    assert labels == {"LetsBall"}             # most-used name wins as the label


class _FakeClient:
    """Two-season chain (2024 renews from 2023), minimal data each."""
    def get_league_metadata(self, key):
        return {"key": key}

    def parse_league_meta(self, raw):
        key = raw["key"]
        if key == "454.l.44006":
            return {"league_key": key, "season": "2024", "name": "L", "num_teams": "2",
                    "renew": "428_32747"}
        return {"league_key": key, "season": "2023", "name": "L", "num_teams": "2"}

    def get_league_standings(self, key):
        return key

    def parse_standings(self, key):
        return [
            {"team_key": f"{key}.t.1", "name": "Alpha", "rank": 1, "playoff_seed": "2",
             "wins": 80, "losses": 70, "ties": 0, "percentage": ".53",
             "games_back": "-", "points_for": "900",
             "managers": [{"nickname": "Al", "email": "al@x.com", "guid": "g1"}]},
            {"team_key": f"{key}.t.2", "name": "Beta", "rank": 2, "playoff_seed": "1",
             "wins": 90, "losses": 60, "ties": 0, "percentage": ".60",
             "games_back": "-", "points_for": "950",
             "managers": [{"nickname": "Be", "email": "be@x.com", "guid": "g2"}]},
        ]

    def get_all_team_rosters(self, key):
        return key

    def parse_all_rosters(self, key):
        return [{"team_key": f"{key}.t.1",
                 "players": [{"player_key": f"{key}.p.1", "name": "Star", "status": "",
                              "eligible_positions": ["PG"]}]}]

    def get_league_draft_results(self, key):
        return key

    def parse_draft_results(self, key):
        return [{"pick": 1, "round": 1, "team_key": f"{key}.t.1", "player_key": f"{key}.p.1"},
                {"pick": 2, "round": 1, "team_key": f"{key}.t.2", "player_key": f"{key}.p.9"}]

    def get_player_names(self, league_key, player_keys, batch=25):
        # resolves the drafted-then-dropped player not on any final roster
        return {k: "Dropped Guy" for k in player_keys}


def test_pull_league_history_stores_all_seasons():
    con = duckdb.connect(":memory:")
    totals = yh.pull_league_history(con, client=_FakeClient(), start_key="454.l.44006")
    assert totals["seasons"] == 2          # walked the renew chain
    assert con.execute("SELECT COUNT(*) FROM yh_seasons").fetchone()[0] == 2

    # regular-season standings derived independently of final rank
    row = con.execute(
        "SELECT final_rank, playoff_seed, regular_season_rank FROM yh_standings "
        "WHERE season=2024 AND team_key='454.l.44006.t.1'"
    ).fetchone()
    assert row == (1, 2, 2)   # champ (final 1), 2-seed, 2nd-best regular record

    # owner identity captured by email
    email = con.execute(
        "SELECT manager_email FROM yh_teams WHERE season=2024 AND team_key='454.l.44006.t.1'"
    ).fetchone()[0]
    assert email == "al@x.com"

    # draft names resolved from rosters where possible
    names = dict(con.execute(
        "SELECT pick, player_name FROM yh_draft WHERE season=2024"
    ).fetchall())
    assert names[1] == "Star"          # resolved from final roster
    assert names[2] == "Dropped Guy"   # resolved via batched player lookup


def test_pull_league_history_is_rerunnable():
    con = duckdb.connect(":memory:")
    yh.pull_league_history(con, client=_FakeClient(), start_key="454.l.44006")
    yh.pull_league_history(con, client=_FakeClient(), start_key="454.l.44006")
    assert con.execute("SELECT COUNT(*) FROM yh_seasons").fetchone()[0] == 2  # no dupes
