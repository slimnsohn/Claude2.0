import copy
import json
import pytest
from pathlib import Path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_PROFILES = [
    {
        "profile_id": "p1",
        "age": 34,
        "sex": "M",
        "race": "white",
        "education": "bachelors",
        "party_id": "lean_rep",
        "approval_rating": 0.6,
        "drift_log": [],
    },
    {
        "profile_id": "p2",
        "age": 52,
        "sex": "F",
        "race": "black",
        "education": "graduate",
        "party_id": "strong_dem",
        "approval_rating": 0.3,
        "drift_log": [],
    },
    {
        "profile_id": "p3",
        "age": 28,
        "sex": "F",
        "race": "hispanic",
        "education": "some_college",
        "party_id": "lean_rep",
        "approval_rating": 0.5,
        "drift_log": [],
    },
]

SAMPLE_EVENT = {
    "date": "2026-03-15",
    "description": "Tax cut passes Senate",
    "affected_segments": {
        "party_id": {
            "lean_rep": {"approval_rating": 0.1},
        }
    },
}


@pytest.fixture
def app(tmp_path):
    data_dir = tmp_path / "data"
    (data_dir / "profiles").mkdir(parents=True)
    (data_dir / "polls").mkdir()
    (data_dir / "events").mkdir()
    (data_dir / "snapshots").mkdir()

    profiles = copy.deepcopy(SAMPLE_PROFILES)
    (data_dir / "profiles" / "registry.json").write_text(json.dumps(profiles))
    (data_dir / "snapshots" / "manifest.json").write_text(json.dumps({"snapshots": []}))

    from server import create_app
    flask_app = create_app(data_dir=str(data_dir))
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


# ---------------------------------------------------------------------------
# POST /api/events — create event
# ---------------------------------------------------------------------------

def test_create_event_returns_201(client):
    resp = client.post("/api/events", json=SAMPLE_EVENT)
    assert resp.status_code == 201


def test_create_event_returns_event_id(client):
    resp = client.post("/api/events", json=SAMPLE_EVENT)
    data = resp.get_json()
    assert "event_id" in data
    assert data["event_id"].startswith("EVT-")


def test_create_event_missing_date_returns_400(client):
    body = {"description": "no date", "affected_segments": {}}
    resp = client.post("/api/events", json=body)
    assert resp.status_code == 400


def test_create_event_missing_description_returns_400(client):
    body = {"date": "2026-03-15", "affected_segments": {}}
    resp = client.post("/api/events", json=body)
    assert resp.status_code == 400


def test_create_event_missing_affected_segments_returns_400(client):
    body = {"date": "2026-03-15", "description": "missing segments"}
    resp = client.post("/api/events", json=body)
    assert resp.status_code == 400


def test_create_event_empty_body_returns_400(client):
    resp = client.post("/api/events", json={})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/events — list events
# ---------------------------------------------------------------------------

def test_list_events_returns_200(client):
    resp = client.get("/api/events")
    assert resp.status_code == 200


def test_list_events_empty_initially(client):
    resp = client.get("/api/events")
    data = resp.get_json()
    assert data == []


def test_list_events_returns_created_event(client):
    client.post("/api/events", json=SAMPLE_EVENT)
    resp = client.get("/api/events")
    data = resp.get_json()
    assert len(data) == 1
    assert data[0]["description"] == SAMPLE_EVENT["description"]


def test_list_events_date_filter_start(client):
    client.post("/api/events", json={**SAMPLE_EVENT, "event_id": "EVT-EARLY", "date": "2026-01-01"})
    client.post("/api/events", json={**SAMPLE_EVENT, "event_id": "EVT-LATE", "date": "2026-06-01"})
    resp = client.get("/api/events?start_date=2026-03-01")
    data = resp.get_json()
    ids = [e["event_id"] for e in data]
    assert "EVT-LATE" in ids
    assert "EVT-EARLY" not in ids


def test_list_events_date_filter_end(client):
    client.post("/api/events", json={**SAMPLE_EVENT, "event_id": "EVT-EARLY", "date": "2026-01-01"})
    client.post("/api/events", json={**SAMPLE_EVENT, "event_id": "EVT-LATE", "date": "2026-06-01"})
    resp = client.get("/api/events?end_date=2026-03-01")
    data = resp.get_json()
    ids = [e["event_id"] for e in data]
    assert "EVT-EARLY" in ids
    assert "EVT-LATE" not in ids


# ---------------------------------------------------------------------------
# POST /api/events/<event_id>/apply
# ---------------------------------------------------------------------------

def test_apply_event_returns_200(client, app):
    create_resp = client.post("/api/events", json=SAMPLE_EVENT)
    event_id = create_resp.get_json()["event_id"]
    resp = client.post(f"/api/events/{event_id}/apply")
    assert resp.status_code == 200


def test_apply_event_returns_profiles_affected(client):
    create_resp = client.post("/api/events", json=SAMPLE_EVENT)
    event_id = create_resp.get_json()["event_id"]
    resp = client.post(f"/api/events/{event_id}/apply")
    data = resp.get_json()
    assert "profiles_affected" in data
    # 3 profiles in registry
    assert data["profiles_affected"] == 3


def test_apply_event_modifies_live_registry(client, app):
    create_resp = client.post("/api/events", json=SAMPLE_EVENT)
    event_id = create_resp.get_json()["event_id"]
    client.post(f"/api/events/{event_id}/apply")

    # Read registry directly from disk
    data_dir = Path(app.config["DATA_DIR"])
    registry = json.loads((data_dir / "profiles" / "registry.json").read_text())

    # p1 and p3 are lean_rep — their approval_rating should have increased by 0.1
    p1 = next(p for p in registry if p["profile_id"] == "p1")
    p3 = next(p for p in registry if p["profile_id"] == "p3")
    assert abs(p1["approval_rating"] - 0.7) < 1e-6
    assert abs(p3["approval_rating"] - 0.6) < 1e-6


def test_apply_event_sets_applied_flag(client, app):
    create_resp = client.post("/api/events", json=SAMPLE_EVENT)
    event_id = create_resp.get_json()["event_id"]
    client.post(f"/api/events/{event_id}/apply")

    # Read event file directly
    data_dir = Path(app.config["DATA_DIR"])
    event_file = data_dir / "events" / f"{event_id}.json"
    event = json.loads(event_file.read_text())
    assert event.get("applied") is True


def test_apply_nonexistent_event_returns_404(client):
    resp = client.post("/api/events/EVT-DOES-NOT-EXIST/apply")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/events/<event_id>/preview
# ---------------------------------------------------------------------------

def test_preview_event_returns_200(client):
    create_resp = client.post("/api/events", json=SAMPLE_EVENT)
    event_id = create_resp.get_json()["event_id"]
    resp = client.get(f"/api/events/{event_id}/preview")
    assert resp.status_code == 200


def test_preview_event_returns_profiles_affected_and_changes(client):
    create_resp = client.post("/api/events", json=SAMPLE_EVENT)
    event_id = create_resp.get_json()["event_id"]
    resp = client.get(f"/api/events/{event_id}/preview")
    data = resp.get_json()
    assert "profiles_affected" in data
    assert "changes" in data


def test_preview_event_does_not_modify_registry(client, app):
    create_resp = client.post("/api/events", json=SAMPLE_EVENT)
    event_id = create_resp.get_json()["event_id"]

    # Read registry before preview
    data_dir = Path(app.config["DATA_DIR"])
    before = json.loads((data_dir / "profiles" / "registry.json").read_text())

    client.get(f"/api/events/{event_id}/preview")

    # Read registry after preview — must be identical
    after = json.loads((data_dir / "profiles" / "registry.json").read_text())
    assert before == after


def test_preview_event_counts_affected_profiles(client):
    create_resp = client.post("/api/events", json=SAMPLE_EVENT)
    event_id = create_resp.get_json()["event_id"]
    resp = client.get(f"/api/events/{event_id}/preview")
    data = resp.get_json()
    # p1 and p3 are lean_rep → 2 profiles affected
    assert data["profiles_affected"] == 2


def test_preview_event_changes_detail(client):
    create_resp = client.post("/api/events", json=SAMPLE_EVENT)
    event_id = create_resp.get_json()["event_id"]
    resp = client.get(f"/api/events/{event_id}/preview")
    data = resp.get_json()
    # Each change entry has profile_id and changes dict
    for entry in data["changes"]:
        assert "profile_id" in entry
        assert "changes" in entry
        assert "approval_rating" in entry["changes"]


def test_preview_event_changes_before_after(client):
    create_resp = client.post("/api/events", json=SAMPLE_EVENT)
    event_id = create_resp.get_json()["event_id"]
    resp = client.get(f"/api/events/{event_id}/preview")
    data = resp.get_json()

    p1_entry = next(e for e in data["changes"] if e["profile_id"] == "p1")
    rating_change = p1_entry["changes"]["approval_rating"]
    assert abs(rating_change["before"] - 0.6) < 1e-6
    assert abs(rating_change["after"] - 0.7) < 1e-6


def test_preview_nonexistent_event_returns_404(client):
    resp = client.get("/api/events/EVT-DOES-NOT-EXIST/preview")
    assert resp.status_code == 404
