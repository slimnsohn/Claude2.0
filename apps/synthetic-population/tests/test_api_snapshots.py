import pytest
import json


@pytest.fixture
def app(tmp_path):
    data_dir = tmp_path / "data"
    (data_dir / "profiles").mkdir(parents=True)
    (data_dir / "polls").mkdir()
    (data_dir / "events").mkdir()
    (data_dir / "snapshots").mkdir()
    profiles = [{"profile_id": "p1", "age": 34, "drift_log": []}]
    (data_dir / "profiles" / "registry.json").write_text(json.dumps(profiles))
    (data_dir / "snapshots" / "manifest.json").write_text(json.dumps({"snapshots": []}))
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from server import create_app
    app = create_app(data_dir=str(data_dir))
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def test_post_creates_snapshot_and_returns_id(client):
    resp = client.post(
        "/api/snapshots",
        data=json.dumps({"date": "2026-03-10", "label": "baseline"}),
        content_type="application/json",
    )
    assert resp.status_code == 201
    body = resp.get_json()
    assert "snapshot_id" in body
    assert body["snapshot_id"].startswith("SNAP-")


def test_get_list_returns_snapshots(client):
    client.post(
        "/api/snapshots",
        data=json.dumps({"date": "2026-03-10", "label": "first"}),
        content_type="application/json",
    )
    resp = client.get("/api/snapshots")
    assert resp.status_code == 200
    snapshots = resp.get_json()
    assert isinstance(snapshots, list)
    assert len(snapshots) == 1
    s = snapshots[0]
    assert s["label"] == "first"
    assert s["date"] == "2026-03-10"
    assert s["profile_count"] == 1
    assert "events_applied_through" in s


def test_get_list_returns_expected_fields(client):
    client.post(
        "/api/snapshots",
        data=json.dumps({"date": "2026-03-15", "label": "mid"}),
        content_type="application/json",
    )
    resp = client.get("/api/snapshots")
    snapshot = resp.get_json()[0]
    for field in ("snapshot_id", "date", "label", "profile_count", "events_applied_through"):
        assert field in snapshot


def test_get_single_returns_metadata(client):
    post_resp = client.post(
        "/api/snapshots",
        data=json.dumps({"date": "2026-03-10", "label": "meta-test"}),
        content_type="application/json",
    )
    snap_id = post_resp.get_json()["snapshot_id"]
    resp = client.get(f"/api/snapshots/{snap_id}")
    assert resp.status_code == 200
    meta = resp.get_json()
    assert meta["snapshot_id"] == snap_id
    assert meta["label"] == "meta-test"
    assert meta["profile_count"] == 1


def test_get_single_not_found_returns_404(client):
    resp = client.get("/api/snapshots/SNAP-NOPE")
    assert resp.status_code == 404


def test_delete_removes_snapshot(client):
    post_resp = client.post(
        "/api/snapshots",
        data=json.dumps({"date": "2026-03-10", "label": "deleteme"}),
        content_type="application/json",
    )
    snap_id = post_resp.get_json()["snapshot_id"]
    del_resp = client.delete(f"/api/snapshots/{snap_id}")
    assert del_resp.status_code == 200
    assert del_resp.get_json() == {"deleted": True}
    list_resp = client.get("/api/snapshots")
    assert list_resp.get_json() == []


def test_delete_nonexistent_returns_404(client):
    resp = client.delete("/api/snapshots/SNAP-DOESNOTEXIST")
    assert resp.status_code == 404


def test_snapshot_profiles_unaffected_by_live_registry_changes(app, client):
    """Snapshot captures profiles at creation time; later registry changes don't affect it."""
    post_resp = client.post(
        "/api/snapshots",
        data=json.dumps({"date": "2026-03-10", "label": "frozen"}),
        content_type="application/json",
    )
    snap_id = post_resp.get_json()["snapshot_id"]

    # Mutate the live registry after the snapshot was taken
    data_dir = app.config["DATA_DIR"]
    registry_path = data_dir / "profiles" / "registry.json"
    new_profiles = [
        {"profile_id": "p1", "age": 34, "drift_log": []},
        {"profile_id": "p2", "age": 99, "drift_log": []},
    ]
    registry_path.write_text(json.dumps(new_profiles))

    # Snapshot metadata should still reflect the original count
    meta_resp = client.get(f"/api/snapshots/{snap_id}")
    meta = meta_resp.get_json()
    assert meta["profile_count"] == 1
