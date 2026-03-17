import pytest
import json
from pathlib import Path


@pytest.fixture
def app(tmp_path):
    data_dir = tmp_path / "data"
    (data_dir / "profiles").mkdir(parents=True)
    (data_dir / "polls").mkdir()
    (data_dir / "events").mkdir()
    (data_dir / "snapshots").mkdir()

    profiles = [
        {
            "profile_id": "p1",
            "age": 34,
            "sex": "M",
            "race": "white",
            "education": "bachelors",
            "party_id": "lean_rep",
            "archetype_id": "A-001",
        },
        {
            "profile_id": "p2",
            "age": 52,
            "sex": "F",
            "race": "black",
            "education": "graduate",
            "party_id": "strong_dem",
            "archetype_id": "A-002",
        },
        {
            "profile_id": "p3",
            "age": 28,
            "sex": "F",
            "race": "hispanic",
            "education": "some_college",
            "party_id": "independent",
            "archetype_id": "A-001",
        },
    ]
    (data_dir / "profiles" / "registry.json").write_text(json.dumps(profiles))
    (data_dir / "snapshots" / "manifest.json").write_text(json.dumps({"snapshots": []}))

    from server import create_app
    app = create_app(data_dir=str(data_dir))
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def test_stats_returns_200(client):
    resp = client.get("/api/stats")
    assert resp.status_code == 200


def test_stats_returns_counts(client):
    resp = client.get("/api/stats")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["profile_count"] == 3
    assert data["archetype_count"] == 2


def test_stats_returns_demographic_summary(client):
    resp = client.get("/api/stats")
    data = resp.get_json()
    assert "demographic_summary" in data
    assert "sex" in data["demographic_summary"]


def test_stats_sex_ratios(client):
    resp = client.get("/api/stats")
    data = resp.get_json()
    sex = data["demographic_summary"]["sex"]
    # 1 M, 2 F out of 3
    assert abs(sex["M"] - round(1 / 3, 4)) < 1e-3
    assert abs(sex["F"] - round(2 / 3, 4)) < 1e-3


def test_stats_polls_run_zero_when_empty(client):
    resp = client.get("/api/stats")
    data = resp.get_json()
    assert data["polls_run"] == 0


def test_stats_polls_run_counts_poll_dirs(app, tmp_path):
    data_dir = Path(app.config["DATA_DIR"])
    (data_dir / "polls" / "POLL-001").mkdir()
    (data_dir / "polls" / "POLL-002").mkdir()
    (data_dir / "polls" / "other-dir").mkdir()  # should not be counted
    client = app.test_client()
    resp = client.get("/api/stats")
    data = resp.get_json()
    assert data["polls_run"] == 2


def test_stats_last_event_date_none_when_empty(client):
    resp = client.get("/api/stats")
    data = resp.get_json()
    assert data["last_event_date"] is None


def test_stats_last_event_date_reads_latest_file(app):
    data_dir = Path(app.config["DATA_DIR"])
    events_dir = data_dir / "events"
    (events_dir / "2026-03-10.json").write_text(json.dumps({"date": "2026-03-10", "label": "early"}))
    (events_dir / "2026-03-15.json").write_text(json.dumps({"date": "2026-03-15", "label": "latest"}))
    client = app.test_client()
    resp = client.get("/api/stats")
    data = resp.get_json()
    assert data["last_event_date"] == "2026-03-15"


def test_stats_empty_registry(app, tmp_path):
    data_dir = Path(app.config["DATA_DIR"])
    (data_dir / "profiles" / "registry.json").write_text(json.dumps([]))
    client = app.test_client()
    resp = client.get("/api/stats")
    data = resp.get_json()
    assert data["profile_count"] == 0
    assert data["archetype_count"] == 0
    assert data["demographic_summary"] == {}


def test_stats_missing_registry(app, tmp_path):
    data_dir = Path(app.config["DATA_DIR"])
    (data_dir / "profiles" / "registry.json").unlink()
    client = app.test_client()
    resp = client.get("/api/stats")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["profile_count"] == 0


def test_stats_race_distribution(client):
    resp = client.get("/api/stats")
    data = resp.get_json()
    race = data["demographic_summary"]["race"]
    # 1 white, 1 black, 1 hispanic
    for group in ("white", "black", "hispanic"):
        assert group in race
        assert abs(race[group] - round(1 / 3, 4)) < 1e-3


def test_stats_education_distribution(client):
    resp = client.get("/api/stats")
    data = resp.get_json()
    edu = data["demographic_summary"]["education"]
    assert "bachelors" in edu
    assert "graduate" in edu
    assert "some_college" in edu


def test_stats_party_id_distribution(client):
    resp = client.get("/api/stats")
    data = resp.get_json()
    party = data["demographic_summary"]["party_id"]
    assert "lean_rep" in party
    assert "strong_dem" in party
    assert "independent" in party
