from datetime import datetime, timezone
from odds_pipeline.identity import matcher


def test_canonical_nba_lakers_variants():
    assert matcher.canonical_team("NBA", "Los Angeles Lakers") == "LAL"
    assert matcher.canonical_team("NBA", "LA Lakers") == "LAL"
    assert matcher.canonical_team("NBA", "Lakers") == "LAL"


def test_canonical_unknown_returns_input_uppercased():
    # Unknown names pass through (with a sentinel) so they show up in
    # the unmatched-games log rather than silently failing.
    result = matcher.canonical_team("NBA", "Some Brand New Team")
    assert result == "SOME BRAND NEW TEAM" or result is None


def test_build_game_id_format():
    commence = datetime(2025, 1, 15, 19, 30, tzinfo=timezone.utc)
    game_id = matcher.build_game_id("NBA", commence, home="LAL", away="BOS")
    assert game_id == "NBA:20250115:BOS@LAL"


def test_match_game_exact_match():
    from odds_pipeline.identity.matcher import OddsEvent, ResultCandidate

    odds = OddsEvent(
        sport="NBA",
        commence_time=datetime(2025, 1, 15, 19, 30, tzinfo=timezone.utc),
        home_team_raw="Los Angeles Lakers",
        away_team_raw="Boston Celtics",
        event_id="evt-1",
    )
    candidates = [
        ResultCandidate(
            sport="NBA",
            commence_time=datetime(2025, 1, 15, 0, 0, tzinfo=timezone.utc),
            home_team_canonical="LAL",
            away_team_canonical="BOS",
            source_game_id="0022400500",
        ),
    ]
    match = matcher.match_game(odds, candidates)
    assert match is not None
    assert match.source_game_id == "0022400500"


def test_match_game_no_match_returns_none():
    from odds_pipeline.identity.matcher import OddsEvent, ResultCandidate

    odds = OddsEvent(
        sport="NBA",
        commence_time=datetime(2025, 1, 15, 19, 30, tzinfo=timezone.utc),
        home_team_raw="Los Angeles Lakers",
        away_team_raw="Boston Celtics",
        event_id="evt-1",
    )
    candidates = [
        ResultCandidate(
            sport="NBA",
            commence_time=datetime(2025, 1, 15, 0, 0, tzinfo=timezone.utc),
            home_team_canonical="MIA",
            away_team_canonical="NYK",
            source_game_id="X",
        ),
    ]
    assert matcher.match_game(odds, candidates) is None
