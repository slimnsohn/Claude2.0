"""Negated-phrasing gates at the three question entry points (audit H2).

The keyword matcher is polarity-blind: "Do you oppose X?" matches X's CES
column and would return the SUPPORT distribution as "yes". Policy: reject
negated question stems with a clear 400/error at every entry gate —
create_poll, benchmarks run/compare, and polymarket /ask.
"""

import json

import pytest

from server import create_app


NEGATED_QUESTION = "Do you oppose building a border wall?"
AFFIRMATIVE_QUESTION = "Do you support building a border wall?"


@pytest.fixture
def app(tmp_path):
    data_dir = tmp_path / "data"
    (data_dir / "profiles").mkdir(parents=True)
    (data_dir / "polls").mkdir()
    profiles = [{
        "profile_id": "p1", "age": 40, "sex": "M", "race": "white",
        "education": "hs_diploma", "party_id": "rep", "archetype_id": "A-001",
        "state": "OH", "urban_rural": "rural", "religion_affiliation": "none",
        "religion_attendance": "never", "backstory": "Test person.",
        "drift_log": [], "primary_news_source": "local",
        "income_source": "wages",
    }]
    (data_dir / "profiles" / "registry.json").write_text(json.dumps(profiles))
    flask_app = create_app(data_dir=str(data_dir))
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


def test_create_poll_rejects_negated_phrasing(client):
    resp = client.post("/api/polls", json={"question": NEGATED_QUESTION})
    assert resp.status_code == 400
    assert "negated phrasing" in resp.get_json()["error"].lower()


def test_benchmarks_run_rejects_negated_phrasing(client):
    resp = client.post(
        "/api/benchmarks/run",
        json={"question": "Do you disapprove of Trump's job performance?"},
    )
    assert resp.status_code == 400
    assert "negated phrasing" in resp.get_json()["error"].lower()


def test_benchmarks_compare_rejects_negated_phrasing(client):
    resp = client.post("/api/benchmarks/compare", json={
        "question": NEGATED_QUESTION,
        "real_results": {"yes": 0.4, "no": 0.5, "unsure": 0.1},
    })
    assert resp.status_code == 400
    assert "negated phrasing" in resp.get_json()["error"].lower()


def test_polymarket_ask_rejects_negated_phrasing(client):
    resp = client.post("/api/polymarket/ask", json={"question": NEGATED_QUESTION})
    assert resp.status_code == 400
    assert "negated phrasing" in resp.get_json()["error"].lower()


def test_affirmative_question_not_blocked_at_create_poll(client):
    resp = client.post("/api/polls", json={"question": AFFIRMATIVE_QUESTION})
    assert resp.status_code == 201
