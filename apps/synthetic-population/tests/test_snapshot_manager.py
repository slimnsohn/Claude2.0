import pytest
import json
from pathlib import Path
from snapshots.manager import SnapshotManager


@pytest.fixture
def manager(tmp_path):
    snapshots_dir = tmp_path / "snapshots"
    snapshots_dir.mkdir()
    profiles_path = tmp_path / "profiles" / "registry.json"
    profiles_path.parent.mkdir()
    profiles = [
        {"profile_id": "p1", "age": 34, "sex": "M", "race": "white", "party_id": "lean_rep",
         "drift_log": [
             {"date": "2026-03-01", "topic": "climate", "position": "oppose", "event_id": "E1"},
             {"date": "2026-03-15", "topic": "taxes", "position": "support", "event_id": "E2"},
         ]},
        {"profile_id": "p2", "age": 52, "sex": "F", "race": "black", "party_id": "strong_dem",
         "drift_log": []},
    ]
    profiles_path.write_text(json.dumps(profiles))
    return SnapshotManager(snapshots_dir=snapshots_dir, registry_path=profiles_path)


def test_create_snapshot(manager):
    snap_id = manager.create(date="2026-03-10", label="pre-election")
    assert snap_id.startswith("SNAP-")
    manifest = manager.list_snapshots()
    assert len(manifest) == 1
    assert manifest[0]["label"] == "pre-election"


def test_load_snapshot_returns_profiles(manager):
    snap_id = manager.create(date="2026-03-10", label="test")
    profiles = manager.load(snap_id)
    assert len(profiles) == 2
    assert profiles[0]["profile_id"] == "p1"


def test_snapshot_is_immutable(manager):
    snap_id = manager.create(date="2026-03-10", label="frozen")
    registry = json.loads(manager.registry_path.read_text())
    registry.append({"profile_id": "p3", "age": 28, "drift_log": []})
    manager.registry_path.write_text(json.dumps(registry))
    profiles = manager.load(snap_id)
    assert len(profiles) == 2


def test_load_with_date_filter_trims_drift_log(manager):
    snap_id = manager.create(date="2026-03-10", label="early")
    profiles = manager.load(snap_id, filter_drift_after="2026-03-10")
    assert len(profiles[0]["drift_log"]) == 1
    assert profiles[0]["drift_log"][0]["date"] == "2026-03-01"


def test_delete_snapshot(manager):
    snap_id = manager.create(date="2026-03-10", label="deleteme")
    manager.delete(snap_id)
    assert len(manager.list_snapshots()) == 0


def test_delete_nonexistent_raises(manager):
    with pytest.raises(KeyError):
        manager.delete("SNAP-NOPE")


def test_get_snapshot_metadata(manager):
    snap_id = manager.create(date="2026-03-10", label="meta")
    meta = manager.get_metadata(snap_id)
    assert meta["profile_count"] == 2
    assert meta["date"] == "2026-03-10"


def test_snapshot_records_events_through(manager):
    snap_id = manager.create(date="2026-03-10", label="events")
    meta = manager.get_metadata(snap_id)
    assert meta["events_applied_through"] == "2026-03-01"
