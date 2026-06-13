import json
import pytest
from pathlib import Path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

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
            "education": "some_college",
            "party_id": "lean_rep",
            "archetype_id": "A-001",
            "state": "MI",
            "urban_rural": "rural",
            "religion_affiliation": "evangelical",
            "religion_attendance": "weekly",
            "backstory": "Test person from Michigan.",
            "drift_log": [],
            "primary_news_source": "fox_news",
            "income_source": "wages",
        },
        {
            "profile_id": "p2",
            "age": 52,
            "sex": "F",
            "race": "black",
            "education": "graduate",
            "party_id": "strong_dem",
            "archetype_id": "A-002",
            "state": "GA",
            "urban_rural": "urban",
            "religion_affiliation": "none",
            "religion_attendance": "never",
            "backstory": "Test person from Georgia.",
            "drift_log": [],
            "primary_news_source": "msnbc",
            "income_source": "wages",
        },
    ]
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
# Helpers
# ---------------------------------------------------------------------------

QUESTION = "Do you support raising the minimum wage to $20/hour?"


def _create_poll(client, snapshot_id="live", question=QUESTION):
    return client.post("/api/polls", json={"question": question, "snapshot_id": snapshot_id})


def _get_first_archetype_id(client, poll_id):
    resp = client.get(f"/api/polls/{poll_id}/prompts")
    prompts = resp.get_json()
    return prompts[0]["archetype_id"]


def _record_response(client, poll_id, archetype_id, opinion="yes"):
    return client.post(
        f"/api/polls/{poll_id}/responses",
        json={
            "archetype_id": archetype_id,
            "response_text": "I think this is a great idea.",
            "opinion": opinion,
            "confidence": 7,
        },
    )


# ---------------------------------------------------------------------------
# POST /api/polls
# ---------------------------------------------------------------------------

def test_create_poll_live_returns_201(client):
    resp = _create_poll(client)
    assert resp.status_code == 201


def test_create_poll_live_returns_poll_id(client):
    resp = _create_poll(client)
    data = resp.get_json()
    assert "poll_id" in data
    assert data["poll_id"].startswith("POLL-")


def test_create_poll_live_status_pending(client):
    resp = _create_poll(client)
    data = resp.get_json()
    assert data["status"] == "pending"


def test_create_poll_missing_question_returns_400(client):
    resp = client.post("/api/polls", json={"snapshot_id": "live"})
    assert resp.status_code == 400


def test_create_poll_unknown_snapshot_returns_404(client):
    resp = client.post("/api/polls", json={"question": QUESTION, "snapshot_id": "SNAP-DOES-NOT-EXIST"})
    assert resp.status_code == 404


def test_create_poll_saves_metadata(client, app):
    resp = _create_poll(client)
    poll_id = resp.get_json()["poll_id"]
    data_dir = Path(app.config["DATA_DIR"])
    meta_path = data_dir / "polls" / poll_id / "metadata.json"
    assert meta_path.exists()
    meta = json.loads(meta_path.read_text())
    assert meta["poll_id"] == poll_id
    assert meta["question"] == QUESTION
    assert meta["snapshot_id"] == "live"
    assert meta["status"] == "pending"
    assert "created_at" in meta
    assert "archetype_count" in meta


def test_create_poll_saves_prompts_json(client, app):
    resp = _create_poll(client)
    poll_id = resp.get_json()["poll_id"]
    data_dir = Path(app.config["DATA_DIR"])
    prompts_path = data_dir / "polls" / poll_id / "prompts.json"
    assert prompts_path.exists()
    prompts = json.loads(prompts_path.read_text())
    assert isinstance(prompts, list)
    assert len(prompts) > 0
    for p in prompts:
        assert "archetype_id" in p
        assert "prompt_text" in p
        assert "weight" in p


def test_create_poll_with_snapshot_id(client, app):
    # Create a snapshot first
    data_dir = Path(app.config["DATA_DIR"])
    from snapshots.manager import SnapshotManager
    manager = SnapshotManager(
        snapshots_dir=data_dir / "snapshots",
        registry_path=data_dir / "profiles" / "registry.json",
    )
    snap_id = manager.create(date="2026-03-01", label="test-snap")

    resp = client.post("/api/polls", json={"question": QUESTION, "snapshot_id": snap_id})
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["poll_id"].startswith("POLL-")


# ---------------------------------------------------------------------------
# GET /api/polls
# ---------------------------------------------------------------------------

def test_list_polls_returns_200(client):
    resp = client.get("/api/polls")
    assert resp.status_code == 200


def test_list_polls_empty_initially(client):
    resp = client.get("/api/polls")
    data = resp.get_json()
    assert data == []


def test_list_polls_contains_created_poll(client):
    _create_poll(client)
    resp = client.get("/api/polls")
    data = resp.get_json()
    assert len(data) == 1
    assert data[0]["question"] == QUESTION


def test_list_polls_multiple_polls(client):
    _create_poll(client, question="Question A?")
    _create_poll(client, question="Question B?")
    resp = client.get("/api/polls")
    data = resp.get_json()
    assert len(data) == 2


def test_list_polls_has_required_fields(client):
    _create_poll(client)
    resp = client.get("/api/polls")
    data = resp.get_json()
    poll = data[0]
    assert "poll_id" in poll
    assert "question" in poll
    assert "date" in poll
    assert "snapshot_id" in poll
    assert "status" in poll


# ---------------------------------------------------------------------------
# GET /api/polls/<poll_id>
# ---------------------------------------------------------------------------

def test_get_poll_returns_200(client):
    create_resp = _create_poll(client)
    poll_id = create_resp.get_json()["poll_id"]
    resp = client.get(f"/api/polls/{poll_id}")
    assert resp.status_code == 200


def test_get_poll_returns_metadata(client):
    create_resp = _create_poll(client)
    poll_id = create_resp.get_json()["poll_id"]
    resp = client.get(f"/api/polls/{poll_id}")
    data = resp.get_json()
    assert data["poll_id"] == poll_id
    assert data["question"] == QUESTION
    assert data["status"] == "pending"


def test_get_poll_not_found_returns_404(client):
    resp = client.get("/api/polls/POLL-DOES-NOT-EXIST")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/polls/<poll_id>/prompts
# ---------------------------------------------------------------------------

def test_get_prompts_returns_200(client):
    create_resp = _create_poll(client)
    poll_id = create_resp.get_json()["poll_id"]
    resp = client.get(f"/api/polls/{poll_id}/prompts")
    assert resp.status_code == 200


def test_get_prompts_returns_list(client):
    create_resp = _create_poll(client)
    poll_id = create_resp.get_json()["poll_id"]
    resp = client.get(f"/api/polls/{poll_id}/prompts")
    data = resp.get_json()
    assert isinstance(data, list)
    assert len(data) > 0


def test_get_prompts_has_required_fields(client):
    create_resp = _create_poll(client)
    poll_id = create_resp.get_json()["poll_id"]
    resp = client.get(f"/api/polls/{poll_id}/prompts")
    data = resp.get_json()
    for item in data:
        assert "archetype_id" in item
        assert "prompt_text" in item
        assert "weight" in item


def test_get_prompts_contains_question_text(client):
    create_resp = _create_poll(client)
    poll_id = create_resp.get_json()["poll_id"]
    resp = client.get(f"/api/polls/{poll_id}/prompts")
    data = resp.get_json()
    # At least one prompt should contain the question
    found = any(QUESTION in item["prompt_text"] for item in data)
    assert found


def test_get_prompts_not_found_returns_404(client):
    resp = client.get("/api/polls/POLL-DOES-NOT-EXIST/prompts")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/polls/<poll_id>/responses
# ---------------------------------------------------------------------------

def test_record_response_returns_201(client):
    create_resp = _create_poll(client)
    poll_id = create_resp.get_json()["poll_id"]
    archetype_id = _get_first_archetype_id(client, poll_id)
    resp = _record_response(client, poll_id, archetype_id)
    assert resp.status_code == 201


def test_record_response_returns_result(client):
    create_resp = _create_poll(client)
    poll_id = create_resp.get_json()["poll_id"]
    archetype_id = _get_first_archetype_id(client, poll_id)
    resp = _record_response(client, poll_id, archetype_id, opinion="yes")
    data = resp.get_json()
    assert data["archetype_id"] == archetype_id
    assert data["response"] == "yes"
    assert "hedge_score" in data
    assert "flags" in data


def test_record_response_saves_to_disk(client, app):
    create_resp = _create_poll(client)
    poll_id = create_resp.get_json()["poll_id"]
    archetype_id = _get_first_archetype_id(client, poll_id)
    _record_response(client, poll_id, archetype_id)
    data_dir = Path(app.config["DATA_DIR"])
    response_file = data_dir / "polls" / poll_id / "responses" / f"{archetype_id}.json"
    assert response_file.exists()


def test_record_response_missing_archetype_id_returns_400(client):
    create_resp = _create_poll(client)
    poll_id = create_resp.get_json()["poll_id"]
    resp = client.post(f"/api/polls/{poll_id}/responses", json={"opinion": "yes"})
    assert resp.status_code == 400


def test_record_response_poll_not_found_returns_404(client):
    resp = client.post(
        "/api/polls/POLL-DOES-NOT-EXIST/responses",
        json={"archetype_id": "A-001", "opinion": "yes"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/polls/<poll_id>/aggregate
# ---------------------------------------------------------------------------

def _setup_poll_with_responses(client):
    """Create poll, record responses for all archetypes, return poll_id."""
    create_resp = _create_poll(client)
    poll_id = create_resp.get_json()["poll_id"]
    prompts = client.get(f"/api/polls/{poll_id}/prompts").get_json()
    opinions = ["yes", "no"]
    for i, p in enumerate(prompts):
        opinion = opinions[i % len(opinions)]
        _record_response(client, poll_id, p["archetype_id"], opinion=opinion)
    return poll_id


def test_aggregate_returns_200(client):
    poll_id = _setup_poll_with_responses(client)
    resp = client.post(f"/api/polls/{poll_id}/aggregate")
    assert resp.status_code == 200


def test_aggregate_returns_distribution(client):
    poll_id = _setup_poll_with_responses(client)
    resp = client.post(f"/api/polls/{poll_id}/aggregate")
    data = resp.get_json()
    assert "distribution" in data
    dist = data["distribution"]
    assert isinstance(dist, dict)
    assert len(dist) > 0


def test_aggregate_sets_status_complete(client, app):
    poll_id = _setup_poll_with_responses(client)
    client.post(f"/api/polls/{poll_id}/aggregate")
    data_dir = Path(app.config["DATA_DIR"])
    meta = json.loads((data_dir / "polls" / poll_id / "metadata.json").read_text())
    assert meta["status"] == "complete"


def test_aggregate_saves_results_json(client, app):
    poll_id = _setup_poll_with_responses(client)
    client.post(f"/api/polls/{poll_id}/aggregate")
    data_dir = Path(app.config["DATA_DIR"])
    results_path = data_dir / "polls" / poll_id / "results.json"
    assert results_path.exists()


def test_aggregate_returns_n_responses(client):
    poll_id = _setup_poll_with_responses(client)
    resp = client.post(f"/api/polls/{poll_id}/aggregate")
    data = resp.get_json()
    assert "n_responses" in data
    assert data["n_responses"] > 0


def test_aggregate_no_responses_returns_400(client):
    create_resp = _create_poll(client)
    poll_id = create_resp.get_json()["poll_id"]
    resp = client.post(f"/api/polls/{poll_id}/aggregate")
    assert resp.status_code == 400


def test_aggregate_poll_not_found_returns_404(client):
    resp = client.post("/api/polls/POLL-DOES-NOT-EXIST/aggregate")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/polls/<poll_id> after aggregate returns distribution
# ---------------------------------------------------------------------------

def test_get_poll_after_aggregate_has_distribution(client):
    poll_id = _setup_poll_with_responses(client)
    client.post(f"/api/polls/{poll_id}/aggregate")
    resp = client.get(f"/api/polls/{poll_id}")
    data = resp.get_json()
    assert data["status"] == "complete"
    assert "distribution" in data
    assert "breakdowns" in data


def test_get_poll_after_aggregate_list_shows_headline(client):
    poll_id = _setup_poll_with_responses(client)
    client.post(f"/api/polls/{poll_id}/aggregate")
    resp = client.get("/api/polls")
    polls = resp.get_json()
    completed = next(p for p in polls if p["poll_id"] == poll_id)
    assert completed["status"] == "complete"
    assert completed["headline_result"] is not None
