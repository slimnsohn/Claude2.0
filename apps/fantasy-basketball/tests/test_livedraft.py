from fbball.livedraft import LiveDraft


def _p(pid, name, value, **z):
    return {"player_id": pid, "full_name": name, "nba_position": "G",
            "total_value": value, "zscores": dict(z), "gp": 70}


def _board():
    # pre-sorted by value desc, like a real board
    return [
        _p(1, "Star Wing", 15.0, PTS=3, REB=1),
        _p(2, "Big Man", 12.0, REB=4, BLK=3),
        _p(3, "Point Guard", 10.0, AST=4, PTS=2),
        _p(4, "Sharpshooter", 8.0, FG3M=4),
    ]


def test_draft_removes_from_available():
    d = LiveDraft(_board())
    d.draft(1)
    assert 1 not in [p["player_id"] for p in d.available()]
    assert d.best(10)[0]["player_id"] == 2   # next best is now top


def test_draft_to_me_builds_my_roster():
    d = LiveDraft(_board())
    d.draft(2, mine=True)
    assert [p["player_id"] for p in d.my_players()] == [2]


def test_undo_reverts_last_pick():
    d = LiveDraft(_board())
    d.draft(1, mine=True)
    d.undo()
    assert 1 in [p["player_id"] for p in d.available()]
    assert d.my_players() == []


def test_double_draft_is_noop():
    d = LiveDraft(_board())
    assert d.draft(1) is True
    assert d.draft(1) is False   # already gone


def test_resolve_matches_by_name_fuzzy():
    d = LiveDraft(_board())
    assert d.resolve("big man")["player_id"] == 2      # case-insensitive
    assert d.resolve("sharpshoter")["player_id"] == 4  # typo tolerated
    assert d.resolve("nobody") is None


def test_resolve_is_accent_insensitive():
    board = [_p(9, "Nikola Jokić", 20.0), _p(8, "Luka Dončić", 18.0)]
    d = LiveDraft(board)
    assert d.resolve("jokic")["player_id"] == 9    # plain-ASCII input matches
    assert d.resolve("doncic")["player_id"] == 8


def test_by_need_prioritizes_my_weak_categories():
    d = LiveDraft(_board())
    # draft a PTS-heavy guard to my team -> I now need REB/BLK, not PTS
    d.draft(1, mine=True)   # Star Wing: PTS heavy
    needs = d.by_need(10)
    # Big Man (REB/BLK) should rank above Point Guard (PTS/AST) for my needs
    order = [p["player_id"] for p in needs]
    assert order.index(2) < order.index(3)
