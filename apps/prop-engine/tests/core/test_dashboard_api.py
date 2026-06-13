import json
from pathlib import Path
import pytest


@pytest.fixture
def app(tmp_path):
    snapshot = tmp_path / "today.json"
    snapshot.write_text(json.dumps({
        "run_id": 1, "generated_at": "2026-05-19T18:00:00",
        "n_plays": 1,
        "plays": [{
            "id": 1, "projection_id": 1, "book": "pinnacle",
            "offered_odds": -110, "edge_pct": 0.05,
            "recommended_stake": 100, "ev_dollars": 5.0,
            "status": "open", "posterior_prob": 0.555,
            "consensus_prob": 0.51, "mu_adjusted": 23.1,
            "residual_breakdown": "{}", "notes": "[]",
            "player_name": "A'ja Wilson", "market_type": "player_points",
            "line_value": 22.5, "side": "over",
            "commence_time": "2026-05-19T23:30:00",
            "event_id": "evt-1",
        }],
    }))
    db_path = tmp_path / "test.db"
    from core.storage import StorageBackend
    StorageBackend(str(db_path)).initialize()
    from core.dashboard.app import create_app
    app = create_app(snapshot_path=str(snapshot), db_path=str(db_path))
    app.config["TESTING"] = True
    return app


def test_api_plays_returns_snapshot(app):
    with app.test_client() as c:
        r = c.get("/api/plays")
        assert r.status_code == 200
        data = r.get_json()
        assert data["n_plays"] == 1
        assert data["plays"][0]["player_name"] == "A'ja Wilson"


def test_api_log_bet_404_when_play_missing(app):
    with app.test_client() as c:
        r = c.post("/api/log_bet", json={
            "play_id": 999, "stake_actual": 100,
            "odds_actual": -110, "book": "pinnacle",
        })
        assert r.status_code == 404


def test_api_plays_empty_when_no_snapshot(tmp_path):
    from core.dashboard.app import create_app
    snapshot = tmp_path / "missing.json"
    db_path = tmp_path / "x.db"
    from core.storage import StorageBackend
    StorageBackend(str(db_path)).initialize()
    app = create_app(snapshot_path=str(snapshot), db_path=str(db_path))
    with app.test_client() as c:
        r = c.get("/api/plays")
        assert r.status_code == 200
        data = r.get_json()
        assert data["n_plays"] == 0
        assert data["plays"] == []
