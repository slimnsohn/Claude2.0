import pytest
import json


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
            "state": "MI",
            "urban_rural": "rural",
            "backstory": "John is a 34-year-old mechanic from Michigan.",
            "drift_log": [],
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
            "backstory": "Sarah is a 52-year-old attorney from Georgia.",
            "drift_log": [],
        },
    ]
    (data_dir / "profiles" / "registry.json").write_text(json.dumps(profiles))
    (data_dir / "snapshots" / "manifest.json").write_text(json.dumps({"snapshots": []}))
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from server import create_app
    application = create_app(data_dir=str(data_dir))
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app):
    return app.test_client()


def test_list_profiles_returns_list(client):
    resp = client.get("/api/profiles")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    assert len(data) == 2


def test_list_profiles_no_backstory(client):
    resp = client.get("/api/profiles")
    data = resp.get_json()
    for profile in data:
        assert "backstory" not in profile
        assert "drift_log" not in profile


def test_list_profiles_has_expected_fields(client):
    resp = client.get("/api/profiles")
    data = resp.get_json()
    expected_keys = {"profile_id", "age", "sex", "race", "education", "state",
                     "party_id", "archetype_id", "urban_rural"}
    for profile in data:
        assert expected_keys == set(profile.keys())


def test_filter_by_sex_male(client):
    resp = client.get("/api/profiles?sex=M")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) == 1
    assert data[0]["profile_id"] == "p1"
    assert data[0]["sex"] == "M"


def test_filter_by_sex_female(client):
    resp = client.get("/api/profiles?sex=F")
    data = resp.get_json()
    assert len(data) == 1
    assert data[0]["profile_id"] == "p2"


def test_filter_by_party_id(client):
    resp = client.get("/api/profiles?party_id=strong_dem")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) == 1
    assert data[0]["party_id"] == "strong_dem"
    assert data[0]["profile_id"] == "p2"


def test_filter_by_party_id_lean_rep(client):
    resp = client.get("/api/profiles?party_id=lean_rep")
    data = resp.get_json()
    assert len(data) == 1
    assert data[0]["profile_id"] == "p1"


def test_filter_by_party_id_no_match(client):
    resp = client.get("/api/profiles?party_id=independent")
    data = resp.get_json()
    assert data == []


def test_filter_by_state(client):
    resp = client.get("/api/profiles?state=MI")
    data = resp.get_json()
    assert len(data) == 1
    assert data[0]["profile_id"] == "p1"


def test_filter_by_race(client):
    resp = client.get("/api/profiles?race=black")
    data = resp.get_json()
    assert len(data) == 1
    assert data[0]["profile_id"] == "p2"


def test_filter_by_urban_rural(client):
    resp = client.get("/api/profiles?urban_rural=urban")
    data = resp.get_json()
    assert len(data) == 1
    assert data[0]["profile_id"] == "p2"


def test_filter_by_archetype_id(client):
    resp = client.get("/api/profiles?archetype_id=A-001")
    data = resp.get_json()
    assert len(data) == 1
    assert data[0]["profile_id"] == "p1"


def test_text_search_matches_backstory(client):
    resp = client.get("/api/profiles?search=mechanic")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) == 1
    assert data[0]["profile_id"] == "p1"


def test_text_search_matches_backstory_case_insensitive(client):
    resp = client.get("/api/profiles?search=ATTORNEY")
    data = resp.get_json()
    assert len(data) == 1
    assert data[0]["profile_id"] == "p2"


def test_text_search_no_match(client):
    resp = client.get("/api/profiles?search=astronaut")
    data = resp.get_json()
    assert data == []


def test_text_search_matches_both(client):
    resp = client.get("/api/profiles?search=year-old")
    data = resp.get_json()
    assert len(data) == 2


def test_get_profile_detail_returns_full_profile(client):
    resp = client.get("/api/profiles/p1")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["profile_id"] == "p1"
    assert data["backstory"] == "John is a 34-year-old mechanic from Michigan."
    assert "drift_log" in data
    assert data["age"] == 34


def test_get_profile_detail_p2(client):
    resp = client.get("/api/profiles/p2")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["profile_id"] == "p2"
    assert "attorney" in data["backstory"]
    assert "drift_log" in data


def test_get_profile_nonexistent_returns_404(client):
    resp = client.get("/api/profiles/nonexistent")
    assert resp.status_code == 404


def test_get_profile_nonexistent_error_message(client):
    resp = client.get("/api/profiles/nonexistent")
    data = resp.get_json()
    assert "error" in data


def test_combined_filters(client):
    resp = client.get("/api/profiles?sex=F&state=GA")
    data = resp.get_json()
    assert len(data) == 1
    assert data[0]["profile_id"] == "p2"


def test_combined_filter_no_match(client):
    resp = client.get("/api/profiles?sex=M&state=GA")
    data = resp.get_json()
    assert data == []
