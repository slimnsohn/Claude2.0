"""Verify backtesting temporal isolation end-to-end."""
import pytest
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def app_with_data(tmp_path):
    data_dir = tmp_path / "data"
    (data_dir / "profiles").mkdir(parents=True)
    (data_dir / "polls").mkdir()
    (data_dir / "events").mkdir()
    (data_dir / "snapshots").mkdir()

    profiles = [
        {"profile_id": "p1", "age": 34, "sex": "M", "race": "white",
         "party_id": "lean_rep", "education": "some_college", "state": "MI",
         "urban_rural": "rural", "archetype_id": "A-001",
         "religion_affiliation": "evangelical", "religion_attendance": "weekly",
         "backstory": "Test person 1.", "climate_policy_support": 0.3,
         "income_source": "wages", "primary_news_source": "fox_news",
         "drift_log": []},
        {"profile_id": "p2", "age": 52, "sex": "F", "race": "black",
         "party_id": "strong_dem", "education": "graduate", "state": "GA",
         "urban_rural": "urban", "archetype_id": "A-002",
         "religion_affiliation": "none", "religion_attendance": "never",
         "backstory": "Test person 2.", "climate_policy_support": 0.8,
         "income_source": "wages", "primary_news_source": "msnbc",
         "drift_log": []},
    ]
    (data_dir / "profiles" / "registry.json").write_text(json.dumps(profiles))
    (data_dir / "snapshots" / "manifest.json").write_text(json.dumps({"snapshots": []}))

    from server import create_app
    app = create_app(data_dir=str(data_dir))
    app.config["TESTING"] = True
    return app, data_dir


def test_snapshot_before_event_has_no_drift(app_with_data):
    """Create snapshot -> apply event -> snapshot profiles are unaffected."""
    app, data_dir = app_with_data
    client = app.test_client()

    # 1. Create snapshot BEFORE any events
    resp = client.post("/api/snapshots", json={"date": "2026-03-01", "label": "pre-event"})
    assert resp.status_code in (200, 201)
    snap_id = resp.get_json()["snapshot_id"]

    # 2. Create and apply an event that shifts climate_policy_support for lean_rep
    resp = client.post("/api/events", json={
        "date": "2026-03-15",
        "description": "EPA ruling",
        "affected_segments": {"party_id": {"lean_rep": {"climate_policy_support": 0.2}}},
    })
    event_id = resp.get_json()["event_id"]
    resp = client.post(f"/api/events/{event_id}/apply")
    assert resp.status_code == 200

    # 3. Live registry should show drift
    live_profiles = json.loads((data_dir / "profiles" / "registry.json").read_text())
    p1_live = next(p for p in live_profiles if p["profile_id"] == "p1")
    assert p1_live["climate_policy_support"] != 0.3  # should have drifted to ~0.5

    # 4. Snapshot profiles should NOT show drift
    from snapshots.manager import SnapshotManager
    mgr = SnapshotManager(data_dir / "snapshots", data_dir / "profiles" / "registry.json")
    snap_profiles = mgr.load(snap_id)
    p1_snap = next(p for p in snap_profiles if p["profile_id"] == "p1")
    assert p1_snap["climate_policy_support"] == 0.3  # unchanged -- snapshot is immutable


def test_snapshot_drift_log_filtered_by_date(app_with_data):
    """Loading a snapshot with date filter should exclude future drift entries."""
    app, data_dir = app_with_data
    client = app.test_client()

    # Manually add drift_log entries with dates to a profile
    profiles = json.loads((data_dir / "profiles" / "registry.json").read_text())
    profiles[0]["drift_log"] = [
        {"date": "2026-02-01", "topic": "taxes", "position": "oppose", "event_id": "E1"},
        {"date": "2026-04-01", "topic": "climate", "position": "support", "event_id": "E2"},
    ]
    (data_dir / "profiles" / "registry.json").write_text(json.dumps(profiles))

    # Create snapshot
    resp = client.post("/api/snapshots", json={"date": "2026-03-01", "label": "mid-point"})
    snap_id = resp.get_json()["snapshot_id"]

    # Load with date filter
    from snapshots.manager import SnapshotManager
    mgr = SnapshotManager(data_dir / "snapshots", data_dir / "profiles" / "registry.json")
    filtered = mgr.load(snap_id, filter_drift_after="2026-03-01")

    # Should only have the Feb entry, not the April one
    assert len(filtered[0]["drift_log"]) == 1
    assert filtered[0]["drift_log"][0]["date"] == "2026-02-01"


def test_multiple_snapshots_independent(app_with_data):
    """Two snapshots created at different times should have independent data."""
    app, data_dir = app_with_data
    client = app.test_client()

    # Create first snapshot
    resp = client.post("/api/snapshots", json={"date": "2026-03-01", "label": "early"})
    snap1 = resp.get_json()["snapshot_id"]

    # Add a profile to live registry
    profiles = json.loads((data_dir / "profiles" / "registry.json").read_text())
    profiles.append({"profile_id": "p3", "age": 28, "drift_log": []})
    (data_dir / "profiles" / "registry.json").write_text(json.dumps(profiles))

    # Create second snapshot
    resp = client.post("/api/snapshots", json={"date": "2026-03-15", "label": "late"})
    snap2 = resp.get_json()["snapshot_id"]

    # First snapshot: 2 profiles. Second: 3 profiles.
    from snapshots.manager import SnapshotManager
    mgr = SnapshotManager(data_dir / "snapshots", data_dir / "profiles" / "registry.json")
    assert len(mgr.load(snap1)) == 2
    assert len(mgr.load(snap2)) == 3
