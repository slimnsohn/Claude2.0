from sports.wnba.ids import normalize_name, fuzzy_match_player


def test_normalize_strips_accents_and_punctuation():
    assert normalize_name("A'ja Wilson") == "aja wilson"
    assert normalize_name("Napheesa Collier") == "napheesa collier"
    assert normalize_name("Brittney Sykes") == "brittney sykes"


def test_fuzzy_match_finds_player():
    roster = [
        {"player_id": "1628932", "full_name": "A'ja Wilson"},
        {"player_id": "1628886", "full_name": "Napheesa Collier"},
    ]
    matched = fuzzy_match_player("aja wilson", roster)
    assert matched["player_id"] == "1628932"


def test_fuzzy_match_returns_none_when_no_close_match():
    roster = [{"player_id": "1", "full_name": "Caitlin Clark"}]
    assert fuzzy_match_player("Lebron James", roster) is None
