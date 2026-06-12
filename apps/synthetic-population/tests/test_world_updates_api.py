import json
from pathlib import Path

import pytest

from server import create_app


@pytest.fixture
def client(tmp_path):
    (tmp_path / "profiles").mkdir(parents=True)
    (tmp_path / "profiles" / "registry.json").write_text(json.dumps([
        {"profile_id": "p1", "party_id": "rep", "primary_news_source": "fox_news",
         "beliefs": {}, "drift_log": []},
    ]))
    app = create_app(data_dir=str(tmp_path))
    app.config["TESTING"] = True
    return app.test_client()


def test_belief_history_empty(client):
    resp = client.get("/api/world-updates/belief-history")
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_calibration_status_none(client):
    resp = client.get("/api/world-updates/calibration-status")
    assert resp.status_code == 200
    assert resp.get_json()["verdict"] == "none"


def test_cycle_endpoint_runs(client, monkeypatch):
    # Patch fetch to avoid network: run_cycle's default fetch is engine.news_fetch.fetch_headlines
    import engine.update_cycle as uc
    monkeypatch.setattr(uc, "fetch_headlines", lambda: [
        {"title": "Economy surges on strong jobs report", "description": "", "feed": "AP"}])
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    resp = client.post("/api/world-updates/cycle")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["n_events"] >= 1
    assert body["scoring_method"] == "keyword"
    assert body["calibration"]["verdict"] in ("pass", "drift_warning", "stale")
