import json
import sqlite3
from pathlib import Path
from odds_pipeline.store import migrate, seed, derive


def test_derive_populates_games_from_odds_archive(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    migrate.init_db(str(db_path))
    seed.seed_all(str(db_path))

    odds_root = tmp_path / "raw" / "odds"
    results_root = tmp_path / "raw" / "results"
    (odds_root / "NBA" / "2025-01-16").mkdir(parents=True)
    (results_root / "NBA").mkdir(parents=True)

    # Fixture: minimal odds payload (single book, single market)
    odds_payload = {
        "_meta": {
            "odds_api_event": {
                "id": "evt-1",
                "commence_time": "2025-01-16T01:00:00Z",
                "home_team": "Los Angeles Lakers",
                "away_team": "Boston Celtics",
            },
            "snapshot_time": "2025-01-16T00:55:00Z",
            "regions": ["us"], "markets": ["h2h"],
        },
        "payload": {
            "id": "evt-1",
            "commence_time": "2025-01-16T01:00:00Z",
            "home_team": "Los Angeles Lakers",
            "away_team": "Boston Celtics",
            "bookmakers": [
                {"key": "draftkings", "title": "DraftKings",
                 "markets": [{"key": "h2h", "outcomes": [
                     {"name": "Los Angeles Lakers", "price": -150},
                     {"name": "Boston Celtics", "price": 130},
                 ]}]},
            ],
        },
    }
    (odds_root / "NBA" / "2025-01-16" / "evt-1__20250116T005500Z.json").write_text(
        json.dumps(odds_payload)
    )

    results_payload = {
        "game_id": "NBA:20250116:BOS@LAL",
        "sport": "NBA",
        "commence_time": "2025-01-16T01:00:00Z",
        "home_team_canonical": "LAL",
        "away_team_canonical": "BOS",
        "source_game_id": "0022400500",
        "segment_scores": {"FULL": [108, 102], "Q1": [24, 28]},
        "went_to_ot": False,
        "raw_payload": {},
    }
    (results_root / "NBA" / "NBA_20250116_BOS_at_LAL.json").write_text(
        json.dumps(results_payload)
    )

    derive.build_all(db_path=str(db_path),
                     odds_root=str(odds_root),
                     results_root=str(results_root))

    conn = sqlite3.connect(db_path)
    games = conn.execute("SELECT game_id, home_team, away_team FROM games").fetchall()
    assert ("NBA:20250116:BOS@LAL", "LAL", "BOS") in games

    odds_rows = conn.execute(
        "SELECT bookmaker_key, market_type, side, price_american, is_close "
        "FROM odds_snapshots WHERE game_id=?",
        ("NBA:20250116:BOS@LAL",),
    ).fetchall()
    assert ("draftkings", "h2h", "home", -150, 1) in odds_rows
    assert ("draftkings", "h2h", "away", 130, 1) in odds_rows

    scores = conn.execute(
        "SELECT segment_key, home_score, away_score FROM scores WHERE game_id=?",
        ("NBA:20250116:BOS@LAL",),
    ).fetchall()
    assert ("FULL", 108, 102) in scores
    assert ("Q1", 24, 28) in scores


def test_derive_is_idempotent(tmp_path):
    db_path = tmp_path / "test.db"
    migrate.init_db(str(db_path))
    seed.seed_all(str(db_path))
    odds_root = tmp_path / "raw" / "odds"
    odds_root.mkdir(parents=True)
    results_root = tmp_path / "raw" / "results"
    results_root.mkdir(parents=True)
    derive.build_all(db_path=str(db_path), odds_root=str(odds_root), results_root=str(results_root))
    derive.build_all(db_path=str(db_path), odds_root=str(odds_root), results_root=str(results_root))
    # No exception = pass
