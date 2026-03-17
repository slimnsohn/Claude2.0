# Synthetic Population Engine — Web UI Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a web UI with sidebar dashboard layout for polling synthetic populations, browsing profiles, managing events, and backtesting against temporal snapshots.

**Architecture:** Flask backend serving a vanilla HTML/CSS/JS single-page app. The Flask server wraps existing Python modules (engine, generator, monitor) behind a REST API. New snapshot module provides immutable population snapshots for backtesting with strict temporal isolation. Claude-in-Chrome integration is orchestrated externally — the server just prepares prompts and records responses.

**Tech Stack:** Python 3.11+, Flask, vanilla HTML/CSS/JS, Canvas API for charts, JSON file storage

**Spec:** `docs/superpowers/specs/2026-03-17-synthetic-population-ui-design.md`

---

## File Structure

```
apps/synthetic-population/
├── server.py                          # Flask app factory + route registration
├── start.bat                          # Updated: installs deps + starts Flask
├── requirements.txt                   # Updated: add flask
│
├── snapshots/
│   ├── __init__.py
│   └── manager.py                     # SnapshotManager: create/load/list/delete snapshots
│
├── api/
│   ├── __init__.py                    # Flask Blueprint registration helper
│   ├── profiles.py                    # GET /api/profiles, GET /api/profiles/:id
│   ├── polls.py                       # CRUD + prepare/record/aggregate poll endpoints
│   ├── snapshots.py                   # CRUD snapshot endpoints
│   ├── events_api.py                  # Event CRUD + drift apply/preview (named to avoid collision with monitor/events.py)
│   └── stats.py                       # GET /api/stats
│
├── static/
│   ├── index.html                     # Single-page app shell + sidebar
│   ├── styles.css                     # Project CSS (uses base.css variables)
│   └── app.js                         # Frontend: routing, views, API calls, charts
│
├── tests/
│   ├── test_snapshot_manager.py       # Snapshot CRUD + isolation tests
│   ├── test_api_profiles.py           # Profile endpoint tests
│   ├── test_api_polls.py             # Poll endpoint tests
│   ├── test_api_snapshots.py          # Snapshot endpoint tests
│   ├── test_api_events.py            # Event endpoint tests
│   ├── test_api_stats.py             # Stats endpoint tests
│   └── test_temporal_isolation.py     # End-to-end backtest isolation verification
│
│   ... (existing files unchanged)
```

---

## Task 1: Project Setup — Flask + Requirements

**Files:**
- Modify: `apps/synthetic-population/requirements.txt`
- Create: `apps/synthetic-population/server.py`
- Modify: `apps/synthetic-population/start.bat`
- Modify: `apps/synthetic-population/.gitignore`

- [ ] **Step 1: Add Flask to requirements.txt**

Append `flask>=3.0` to requirements.txt.

- [ ] **Step 2: Install Flask**

Run: `cd apps/synthetic-population && pip install flask>=3.0`

- [ ] **Step 3: Create minimal server.py**

```python
import sys
from pathlib import Path
from flask import Flask

# Ensure project modules are importable
sys.path.insert(0, str(Path(__file__).parent))

def create_app(data_dir: str = None) -> Flask:
    app = Flask(__name__, static_folder="static", static_url_path="/static")

    # Data directory defaults to ./data
    app.config["DATA_DIR"] = Path(data_dir) if data_dir else Path(__file__).parent / "data"

    # Serve index.html at root
    @app.route("/")
    def index():
        return app.send_static_file("index.html")

    # Serve workspace shared assets
    @app.route("/_shared/<path:filename>")
    def shared_assets(filename):
        shared_dir = Path(__file__).parent.parent.parent / "_shared"
        return Flask.send_from_directory(app, str(shared_dir), filename)

    @app.route("/_skills/<path:filename>")
    def skill_assets(filename):
        skills_dir = Path(__file__).parent.parent.parent / "_skills"
        return Flask.send_from_directory(app, str(skills_dir), filename)

    return app

if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=5000)
```

- [ ] **Step 4: Create placeholder static/index.html**

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Synthetic Population Engine</title>
</head>
<body>
    <h1>Synthetic Population Engine</h1>
    <p>Loading...</p>
</body>
</html>
```

- [ ] **Step 5: Update start.bat**

```bat
@echo off
cd /d "%~dp0"
pip install -r requirements.txt -q
python server.py
```

- [ ] **Step 6: Add data/snapshots/ to .gitignore**

Append `data/snapshots/` to existing .gitignore.

- [ ] **Step 7: Verify server starts**

Run: `cd apps/synthetic-population && python server.py &` then `curl http://localhost:5000/`
Expected: HTML page returned

- [ ] **Step 8: Commit**

```bash
git add apps/synthetic-population/server.py apps/synthetic-population/static/index.html apps/synthetic-population/requirements.txt apps/synthetic-population/start.bat apps/synthetic-population/.gitignore
git commit -m "scaffold: Flask server with static file serving"
```

---

## Task 2: Snapshot Manager

**Files:**
- Create: `apps/synthetic-population/snapshots/__init__.py`
- Create: `apps/synthetic-population/snapshots/manager.py`
- Create: `apps/synthetic-population/tests/test_snapshot_manager.py`

This is the core backtesting infrastructure. Must be solid — temporal isolation depends on it.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_snapshot_manager.py
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
    # Write sample registry
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
    """Modifying live registry doesn't affect snapshot."""
    snap_id = manager.create(date="2026-03-10", label="frozen")
    # Modify live registry
    registry = json.loads(manager.registry_path.read_text())
    registry.append({"profile_id": "p3", "age": 28, "drift_log": []})
    manager.registry_path.write_text(json.dumps(registry))
    # Snapshot still has 2
    profiles = manager.load(snap_id)
    assert len(profiles) == 2

def test_load_with_date_filter_trims_drift_log(manager):
    """When loading for backtest, drift_log entries after snapshot date are excluded."""
    snap_id = manager.create(date="2026-03-10", label="early")
    profiles = manager.load(snap_id, filter_drift_after="2026-03-10")
    # p1 has drift on 2026-03-01 (keep) and 2026-03-15 (remove)
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
    """Snapshot metadata should track the latest event date from drift_logs."""
    snap_id = manager.create(date="2026-03-10", label="events")
    meta = manager.get_metadata(snap_id)
    # Latest drift_log date before 2026-03-10 is 2026-03-01
    assert meta["events_applied_through"] == "2026-03-01"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/synthetic-population && python -m pytest tests/test_snapshot_manager.py -v`
Expected: FAIL — module doesn't exist

- [ ] **Step 3: Implement snapshots/manager.py**

```python
import json
import copy
from pathlib import Path
from datetime import datetime

class SnapshotManager:
    """Manages immutable population snapshots for backtesting."""

    def __init__(self, snapshots_dir: Path, registry_path: Path):
        self.snapshots_dir = Path(snapshots_dir)
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.registry_path = Path(registry_path)
        self.manifest_path = self.snapshots_dir / "manifest.json"
        if not self.manifest_path.exists():
            self.manifest_path.write_text(json.dumps({"snapshots": []}))

    def _read_manifest(self) -> dict:
        return json.loads(self.manifest_path.read_text())

    def _write_manifest(self, manifest: dict):
        self.manifest_path.write_text(json.dumps(manifest, indent=2))

    def create(self, date: str, label: str) -> str:
        """Create a snapshot from the current registry. Returns snapshot_id."""
        slug = label.lower().replace(" ", "-")[:30]
        snap_id = f"SNAP-{date.replace('-', '')}-{slug}"

        # Read current registry
        profiles = json.loads(self.registry_path.read_text())

        # Find latest event date from drift_logs that's <= snapshot date
        event_dates = []
        for p in profiles:
            for entry in p.get("drift_log", []):
                d = entry.get("date", "")
                if d and d <= date:
                    event_dates.append(d)
        events_through = max(event_dates) if event_dates else None

        # Save snapshot file (deep copy of profiles)
        snap_file = self.snapshots_dir / f"{snap_id}.json"
        snap_file.write_text(json.dumps(profiles, indent=2, default=str))

        # Update manifest
        manifest = self._read_manifest()
        manifest["snapshots"].append({
            "snapshot_id": snap_id,
            "date": date,
            "label": label,
            "profile_count": len(profiles),
            "events_applied_through": events_through,
            "created_at": datetime.now().isoformat(),
            "file": f"{snap_id}.json",
        })
        self._write_manifest(manifest)

        return snap_id

    def load(self, snapshot_id: str, filter_drift_after: str = None) -> list[dict]:
        """Load profiles from a snapshot.

        If filter_drift_after is set, removes drift_log entries dated after that date.
        This enforces temporal isolation for backtesting.
        """
        meta = self.get_metadata(snapshot_id)
        snap_file = self.snapshots_dir / meta["file"]
        profiles = json.loads(snap_file.read_text())

        if filter_drift_after:
            profiles = copy.deepcopy(profiles)
            for p in profiles:
                p["drift_log"] = [
                    entry for entry in p.get("drift_log", [])
                    if entry.get("date", "") <= filter_drift_after
                ]

        return profiles

    def list_snapshots(self) -> list[dict]:
        """Return list of snapshot metadata dicts."""
        manifest = self._read_manifest()
        return manifest["snapshots"]

    def get_metadata(self, snapshot_id: str) -> dict:
        """Return metadata for a single snapshot."""
        for snap in self.list_snapshots():
            if snap["snapshot_id"] == snapshot_id:
                return snap
        raise KeyError(f"Snapshot '{snapshot_id}' not found")

    def delete(self, snapshot_id: str):
        """Delete a snapshot file and manifest entry."""
        meta = self.get_metadata(snapshot_id)  # raises KeyError if not found
        snap_file = self.snapshots_dir / meta["file"]
        if snap_file.exists():
            snap_file.unlink()
        manifest = self._read_manifest()
        manifest["snapshots"] = [s for s in manifest["snapshots"] if s["snapshot_id"] != snapshot_id]
        self._write_manifest(manifest)
```

- [ ] **Step 4: Create snapshots/__init__.py** (empty)

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd apps/synthetic-population && python -m pytest tests/test_snapshot_manager.py -v`
Expected: All 8 tests PASS

- [ ] **Step 6: Commit**

```bash
git add apps/synthetic-population/snapshots/ apps/synthetic-population/tests/test_snapshot_manager.py
git commit -m "feat: snapshot manager with temporal isolation for backtesting"
```

---

## Task 3: API — Stats Endpoint

**Files:**
- Create: `apps/synthetic-population/api/__init__.py`
- Create: `apps/synthetic-population/api/stats.py`
- Create: `apps/synthetic-population/tests/test_api_stats.py`
- Modify: `apps/synthetic-population/server.py` (register blueprint)

- [ ] **Step 1: Write failing tests**

```python
# tests/test_api_stats.py
import pytest
import json
from pathlib import Path

@pytest.fixture
def app(tmp_path):
    # Set up data directory with sample registry
    data_dir = tmp_path / "data"
    (data_dir / "profiles").mkdir(parents=True)
    (data_dir / "polls").mkdir()
    (data_dir / "events").mkdir()
    (data_dir / "snapshots").mkdir()
    profiles = [
        {"profile_id": "p1", "age": 34, "sex": "M", "race": "white", "education": "bachelors",
         "party_id": "lean_rep", "archetype_id": "A-001"},
        {"profile_id": "p2", "age": 52, "sex": "F", "race": "black", "education": "graduate",
         "party_id": "strong_dem", "archetype_id": "A-002"},
        {"profile_id": "p3", "age": 28, "sex": "F", "race": "hispanic", "education": "some_college",
         "party_id": "independent", "archetype_id": "A-001"},
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

def test_stats_returns_counts(client):
    resp = client.get("/api/stats")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["profile_count"] == 3
    assert data["archetype_count"] == 2  # A-001 and A-002

def test_stats_returns_demographic_summary(client):
    resp = client.get("/api/stats")
    data = resp.get_json()
    assert "demographic_summary" in data
    assert "sex" in data["demographic_summary"]
    assert data["demographic_summary"]["sex"]["M"] == pytest.approx(1/3, abs=0.01)
```

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Implement api/__init__.py**

```python
# Helper for blueprint registration
def register_blueprints(app):
    from api.stats import stats_bp
    app.register_blueprint(stats_bp)
```

- [ ] **Step 4: Implement api/stats.py**

```python
import json
from pathlib import Path
from flask import Blueprint, current_app, jsonify

stats_bp = Blueprint("stats", __name__)

def _load_registry():
    data_dir = Path(current_app.config["DATA_DIR"])
    registry_path = data_dir / "profiles" / "registry.json"
    if registry_path.exists():
        return json.loads(registry_path.read_text())
    return []

@stats_bp.route("/api/stats")
def get_stats():
    profiles = _load_registry()
    data_dir = Path(current_app.config["DATA_DIR"])

    # Count polls
    polls_dir = data_dir / "polls"
    polls_run = len(list(polls_dir.glob("POLL-*"))) if polls_dir.exists() else 0

    # Count events
    events_dir = data_dir / "events"
    events = sorted(events_dir.glob("*.json")) if events_dir.exists() else []
    last_event_date = None
    if events:
        import json as j
        last_evt = j.loads(events[-1].read_text())
        last_event_date = last_evt.get("date")

    # Demographic summary
    demo_summary = {}
    for var in ["sex", "race", "education", "party_id"]:
        counts = {}
        for p in profiles:
            val = p.get(var)
            if val:
                counts[val] = counts.get(val, 0) + 1
        total = sum(counts.values())
        demo_summary[var] = {k: round(v / total, 4) for k, v in counts.items()} if total else {}

    archetype_ids = set(p.get("archetype_id") for p in profiles if p.get("archetype_id"))

    return jsonify({
        "profile_count": len(profiles),
        "archetype_count": len(archetype_ids),
        "polls_run": polls_run,
        "last_event_date": last_event_date,
        "demographic_summary": demo_summary,
    })
```

- [ ] **Step 5: Update server.py to register blueprints**

Add to `create_app()` after config setup:
```python
    from api import register_blueprints
    register_blueprints(app)
```

Update `register_blueprints` to include stats_bp (already done in Step 3).

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd apps/synthetic-population && python -m pytest tests/test_api_stats.py -v`

- [ ] **Step 7: Commit**

```bash
git commit -m "feat: stats API endpoint with demographic summary"
```

---

## Task 4: API — Profiles Endpoints

**Files:**
- Create: `apps/synthetic-population/api/profiles.py`
- Create: `apps/synthetic-population/tests/test_api_profiles.py`
- Modify: `apps/synthetic-population/api/__init__.py` (register blueprint)

- [ ] **Step 1: Write failing tests**

Tests should cover: listing profiles (returns summaries without backstory), filtering by sex/race/education/party_id/state/archetype_id, text search (matches backstory/state/occupation), getting single profile by profile_id (returns full profile with backstory+drift_log), 404 for nonexistent profile.

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Implement api/profiles.py**

Blueprint with:
- `GET /api/profiles` — loads registry, applies query param filters, returns summary list (excludes backstory for performance, includes: profile_id, age, sex, race, education, state, party_id, archetype_id, urban_rural, first name extracted from backstory)
- `GET /api/profiles/<profile_id>` — returns full profile dict

- [ ] **Step 4: Register blueprint in api/__init__.py**

- [ ] **Step 5: Run tests to verify they pass**

- [ ] **Step 6: Commit**

```bash
git commit -m "feat: profiles API with filtering and detail view"
```

---

## Task 5: API — Snapshots Endpoints

**Files:**
- Create: `apps/synthetic-population/api/snapshots.py`
- Create: `apps/synthetic-population/tests/test_api_snapshots.py`
- Modify: `apps/synthetic-population/api/__init__.py`

- [ ] **Step 1: Write failing tests**

Tests should cover: POST to create snapshot (returns snapshot_id), GET list of snapshots, GET single snapshot metadata, DELETE snapshot, 404 for nonexistent, verify snapshot profiles don't change when live registry changes.

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Implement api/snapshots.py**

Blueprint wrapping `SnapshotManager`:
- `POST /api/snapshots` — body: `{date, label}`, creates snapshot, returns `{snapshot_id}`
- `GET /api/snapshots` — returns list from manifest
- `GET /api/snapshots/<id>` — returns metadata
- `DELETE /api/snapshots/<id>` — deletes snapshot

- [ ] **Step 4: Register blueprint**

- [ ] **Step 5: Run tests to verify they pass**

- [ ] **Step 6: Commit**

```bash
git commit -m "feat: snapshots API for backtest management"
```

---

## Task 6: API — Events Endpoints

**Files:**
- Create: `apps/synthetic-population/api/events_api.py`
- Create: `apps/synthetic-population/tests/test_api_events.py`
- Modify: `apps/synthetic-population/api/__init__.py`

- [ ] **Step 1: Write failing tests**

Tests should cover: POST to create event (validates required fields), GET event list (with date range filtering), POST apply drift (modifies live registry, returns affected count), GET preview (returns changes without applying), verify applied flag is set after drift.

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Implement api/events_api.py**

Blueprint wrapping `EventStore` and `DriftEngine`:
- `GET /api/events` — list events, optional start_date/end_date params
- `POST /api/events` — create event, returns event_id
- `POST /api/events/<id>/apply` — loads registry, applies drift via `DriftEngine.apply_batch`, saves updated registry, marks event applied
- `GET /api/events/<id>/preview` — computes drift changes without saving

The apply endpoint must:
1. Load current registry
2. Load the event
3. Run `DriftEngine.apply_batch(profiles, event)`
4. Save updated profiles back to registry.json
5. Track which events have been applied (add `"applied": true` flag to event file)

- [ ] **Step 4: Register blueprint**

- [ ] **Step 5: Run tests to verify they pass**

- [ ] **Step 6: Commit**

```bash
git commit -m "feat: events API with drift apply and preview"
```

---

## Task 7: API — Polls Endpoints

**Files:**
- Create: `apps/synthetic-population/api/polls.py`
- Create: `apps/synthetic-population/tests/test_api_polls.py`
- Modify: `apps/synthetic-population/api/__init__.py`

This is the most complex API — it orchestrates the full polling flow.

- [ ] **Step 1: Write failing tests**

Tests should cover:
- POST create poll with "live" snapshot — creates poll dir, generates prompts, returns poll_id
- POST create poll with snapshot_id — loads snapshot profiles instead of live
- GET list polls — returns recent polls with status
- GET poll detail — returns full results after aggregation
- GET poll prompts — returns prompt list for Claude automation
- POST record response — stores response, runs integrity check
- POST aggregate — runs aggregation, sets status to complete
- Verify poll metadata includes snapshot_id and events_applied_through

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Implement api/polls.py**

Blueprint wrapping `PollRunner`, `ArchetypeBuilder`, `SnapshotManager`:

`POST /api/polls`:
1. Read `{question, snapshot_id}` from body
2. If snapshot_id == "live": load registry.json, else load snapshot (with drift_log filtered to snapshot date)
3. Build archetypes from profiles → get weights
4. Create PollRunner, call `prepare(question, profiles, weights)`
5. Save prompts as JSON (structured: `[{archetype_id, prompt_text, weight}]`)
6. Save poll metadata: `{poll_id, question, snapshot_id, status: "pending", created_at, archetype_count}`
7. Return `{poll_id, status: "pending"}`

`GET /api/polls`: Scan polls dir, return list sorted by date

`GET /api/polls/<id>`: Return full results (or status if not yet complete)

`GET /api/polls/<id>/prompts`: Return structured prompt list

`POST /api/polls/<id>/responses`: Record single archetype response via `PollRunner.record_response()`

`POST /api/polls/<id>/aggregate`: Run `PollRunner.aggregate()`, save results, set status to "complete"

- [ ] **Step 4: Register blueprint**

- [ ] **Step 5: Run tests to verify they pass**

- [ ] **Step 6: Commit**

```bash
git commit -m "feat: polls API with snapshot-aware prompt generation"
```

---

## Task 8: Temporal Isolation Integration Tests

**Files:**
- Create: `apps/synthetic-population/tests/test_temporal_isolation.py`

- [ ] **Step 1: Write integration tests**

End-to-end test verifying temporal isolation:

```python
# tests/test_temporal_isolation.py
"""Verify backtesting temporal isolation end-to-end."""
import pytest
import json
from pathlib import Path

@pytest.fixture
def app_with_data(tmp_path):
    """Set up Flask app with populated registry and events."""
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
         "drift_log": []},
        {"profile_id": "p2", "age": 52, "sex": "F", "race": "black",
         "party_id": "strong_dem", "education": "graduate", "state": "GA",
         "urban_rural": "urban", "archetype_id": "A-002",
         "religion_affiliation": "none", "religion_attendance": "never",
         "backstory": "Test person 2.", "climate_policy_support": 0.8,
         "drift_log": []},
    ]
    (data_dir / "profiles" / "registry.json").write_text(json.dumps(profiles))
    (data_dir / "snapshots" / "manifest.json").write_text(json.dumps({"snapshots": []}))

    from server import create_app
    app = create_app(data_dir=str(data_dir))
    app.config["TESTING"] = True
    return app, data_dir

def test_snapshot_before_event_has_no_drift(app_with_data):
    """Create snapshot → apply event → snapshot profiles are unaffected."""
    app, data_dir = app_with_data
    client = app.test_client()

    # 1. Create snapshot BEFORE any events
    resp = client.post("/api/snapshots", json={"date": "2026-03-01", "label": "pre-event"})
    assert resp.status_code == 200
    snap_id = resp.get_json()["snapshot_id"]

    # 2. Create and apply an event that shifts climate_policy_support
    resp = client.post("/api/events", json={
        "date": "2026-03-15",
        "description": "EPA ruling",
        "affected_segments": {"party_id": {"lean_rep": {"climate_policy_support": 0.2}}},
    })
    event_id = resp.get_json()["event_id"]
    client.post(f"/api/events/{event_id}/apply")

    # 3. Live registry should show drift
    live_profiles = json.loads((data_dir / "profiles" / "registry.json").read_text())
    p1_live = next(p for p in live_profiles if p["profile_id"] == "p1")
    assert p1_live["climate_policy_support"] != 0.3  # drifted

    # 4. Snapshot profiles should NOT show drift
    resp = client.get(f"/api/snapshots/{snap_id}")
    snap_meta = resp.get_json()
    from snapshots.manager import SnapshotManager
    mgr = SnapshotManager(data_dir / "snapshots", data_dir / "profiles" / "registry.json")
    snap_profiles = mgr.load(snap_id)
    p1_snap = next(p for p in snap_profiles if p["profile_id"] == "p1")
    assert p1_snap["climate_policy_support"] == 0.3  # unchanged

def test_poll_with_snapshot_uses_frozen_profiles(app_with_data):
    """A poll against a pre-event snapshot should use the pre-event profile state."""
    app, data_dir = app_with_data
    client = app.test_client()

    # Create snapshot
    resp = client.post("/api/snapshots", json={"date": "2026-03-01", "label": "frozen"})
    snap_id = resp.get_json()["snapshot_id"]

    # Create poll against snapshot
    resp = client.post("/api/polls", json={"question": "Test?", "snapshot_id": snap_id})
    assert resp.status_code == 200
    poll_data = resp.get_json()
    assert poll_data["status"] == "pending"

    # Verify the poll metadata references the snapshot
    poll_id = poll_data["poll_id"]
    resp = client.get(f"/api/polls/{poll_id}")
    detail = resp.get_json()
    assert detail["snapshot_id"] == snap_id
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd apps/synthetic-population && python -m pytest tests/test_temporal_isolation.py -v`

- [ ] **Step 3: Commit**

```bash
git commit -m "test: temporal isolation integration tests for backtesting"
```

---

## Task 9: Frontend — HTML Shell + CSS + Sidebar

**Files:**
- Modify: `apps/synthetic-population/static/index.html`
- Create: `apps/synthetic-population/static/styles.css`
- Create: `apps/synthetic-population/static/app.js`

- [ ] **Step 1: Build index.html**

Single-page app shell with:
- Link to `/_shared/styles/base.css` for theme variables
- Link to `styles.css` for project CSS
- Sidebar: app title, nav links (Poll, Results, Population, Backtest, Events), population stats section
- Main content area: `<main id="app"></main>` where views render
- Script tags: `/_shared/fetch-wrapper.js`, `app.js`, chat widget

The sidebar nav uses `data-view` attributes. Clicking a nav link sets the active view. `app.js` handles routing by reading the active view and calling the appropriate render function.

- [ ] **Step 2: Build styles.css**

Project CSS using base.css variables. Must include:
- Sidebar layout (fixed left, 220px wide, full height)
- Main content area (margin-left: 220px)
- Nav link styles (active state with accent background)
- Population stats in sidebar footer
- Card, table, filter, badge, button styles matching workspace conventions
- Slide-out detail panel (position: fixed, right: 0, width: 400px)
- Chart containers
- Responsive: sidebar collapses to top bar on mobile

- [ ] **Step 3: Build app.js skeleton**

```javascript
// State
let currentView = "poll";
let stats = {};

// Router
function navigate(view) {
    currentView = view;
    document.querySelectorAll(".nav-link").forEach(el => {
        el.classList.toggle("active", el.dataset.view === view);
    });
    render();
}

// Main render
function render() {
    const app = document.getElementById("app");
    switch (currentView) {
        case "poll": renderPollView(app); break;
        case "results": renderResultsView(app); break;
        case "population": renderPopulationView(app); break;
        case "backtest": renderBacktestView(app); break;
        case "events": renderEventsView(app); break;
    }
}

// Placeholder views
function renderPollView(el) { el.innerHTML = "<h2>Poll</h2><p>Coming soon...</p>"; }
function renderResultsView(el) { el.innerHTML = "<h2>Results</h2><p>Coming soon...</p>"; }
function renderPopulationView(el) { el.innerHTML = "<h2>Population</h2><p>Coming soon...</p>"; }
function renderBacktestView(el) { el.innerHTML = "<h2>Backtest</h2><p>Coming soon...</p>"; }
function renderEventsView(el) { el.innerHTML = "<h2>Events</h2><p>Coming soon...</p>"; }

// API helpers
async function api(path, opts = {}) {
    const resp = await fetch(path, {
        headers: { "Content-Type": "application/json" },
        ...opts,
        body: opts.body ? JSON.stringify(opts.body) : undefined,
    });
    return resp.json();
}

// Load stats for sidebar
async function loadStats() {
    stats = await api("/api/stats");
    document.getElementById("stat-profiles").textContent = stats.profile_count || 0;
    document.getElementById("stat-archetypes").textContent = stats.archetype_count || 0;
    document.getElementById("stat-polls").textContent = stats.polls_run || 0;
}

// Init
document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".nav-link").forEach(el => {
        el.addEventListener("click", () => navigate(el.dataset.view));
    });
    loadStats();
    render();
});
```

- [ ] **Step 4: Verify app loads in browser**

Run: `cd apps/synthetic-population && python server.py &` then open http://localhost:5000
Expected: Sidebar with nav links, stats populated, "Coming soon" in main area

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: frontend shell with sidebar layout and routing"
```

---

## Task 10: Frontend — Poll View

**Files:**
- Modify: `apps/synthetic-population/static/app.js` (implement `renderPollView`)

- [ ] **Step 1: Implement renderPollView**

Renders:
- Question textarea with placeholder "Ask your population anything..."
- Snapshot selector dropdown (populated from GET /api/snapshots + "Current Population (live)" default)
- "Run Poll" button (accent color)
- Progress text area (hidden until poll is running)
- Recent polls table (from GET /api/polls, last 10, click navigates to results)

"Run Poll" calls POST /api/polls, then shows progress text. UI polls GET /api/polls/{id} every 3 seconds until status is "complete", then navigates to results.

- [ ] **Step 2: Verify in browser**

- [ ] **Step 3: Commit**

```bash
git commit -m "feat: poll view with question input and snapshot selector"
```

---

## Task 11: Frontend — Population View

**Files:**
- Modify: `apps/synthetic-population/static/app.js` (implement `renderPopulationView`)

- [ ] **Step 1: Implement renderPopulationView**

Renders:
- Filter bar: text search input + dropdown filters (sex, race, education, party_id, state, archetype_id)
- Quick filter buttons: "Democrats", "Republicans", "College+", "Rural", "65+"
- Profile table: columns Name, Age, Sex, Race, Education, State, Party, Archetype. Sortable by clicking column headers.
- Data from GET /api/profiles with filter params
- Click row → opens slide-out detail panel

- [ ] **Step 2: Implement slide-out detail panel**

Fixed position panel on right side (400px wide). Shows:
- Full backstory (highlighted block at top)
- Demographics grouped by category
- Drift log timeline
- Close button (X)

Data from GET /api/profiles/{id}

- [ ] **Step 3: Verify in browser**

- [ ] **Step 4: Commit**

```bash
git commit -m "feat: population browser with filterable table and detail panel"
```

---

## Task 12: Frontend — Results View

**Files:**
- Modify: `apps/synthetic-population/static/app.js` (implement `renderResultsView`)

- [ ] **Step 1: Implement renderResultsView**

Renders (when a poll_id is selected):
- Header: question text, date, snapshot badge (blue="live", orange=backtest with label)
- Headline numbers: large yes/no/unsure percentages with CI ranges
- Mean confidence score
- Demographic breakdowns: collapsible sections with horizontal stacked bars (canvas)
- Time series chart: polls with same question over time (canvas line chart)
- Raw responses table (expandable)

Uses GET /api/polls/{id} for data. For time series, GET /api/polls filtered by matching question text.

- [ ] **Step 2: Implement canvas chart helpers**

Two chart functions:
- `drawStackedBar(canvas, data)` — horizontal stacked bar for demographic breakdowns
- `drawTimeSeries(canvas, polls)` — line chart for poll tracking over time

Both read theme colors via `getComputedStyle()` for seamless dark/light support.

- [ ] **Step 3: Verify in browser**

- [ ] **Step 4: Commit**

```bash
git commit -m "feat: results view with demographic breakdowns and time series charts"
```

---

## Task 13: Frontend — Backtest View

**Files:**
- Modify: `apps/synthetic-population/static/app.js` (implement `renderBacktestView`)

- [ ] **Step 1: Implement renderBacktestView**

Renders:
- Snapshot list table: Date, Label, Profile Count, Events Through, Delete button
- Create snapshot form: date input (default today), label input, "Save Snapshot" button
- Timeline visualization: canvas drawing with snapshot dots (blue) and event markers (orange) on a horizontal axis. Click snapshot to navigate to poll view with it pre-selected.
- Comparison launcher: two snapshot dropdowns (+ "live" option), question input, "Compare" button

"Compare" creates two polls (one per snapshot), then navigates to results in comparison mode.

- [ ] **Step 2: Verify in browser**

- [ ] **Step 3: Commit**

```bash
git commit -m "feat: backtest view with snapshot management and timeline"
```

---

## Task 14: Frontend — Events View

**Files:**
- Modify: `apps/synthetic-population/static/app.js` (implement `renderEventsView`)

- [ ] **Step 1: Implement renderEventsView**

Renders:
- Event log table: Date, Description, Segments (summary), Applied (badge), Actions
- Add event form: date input, description textarea, segment builder (dropdown for variable, value checkboxes, delta input), "Add Event" button
- Per-event actions: "Preview" (shows impact), "Apply" (with confirmation)
- Impact preview: expandable section showing profiles affected, archetype breakdown, magnitude

- [ ] **Step 2: Verify in browser**

- [ ] **Step 3: Commit**

```bash
git commit -m "feat: events view with drift preview and apply"
```

---

## Task 15: Chat Widget Integration

**Files:**
- Modify: `apps/synthetic-population/static/index.html`

- [ ] **Step 1: Add chat widget config and script**

Add before closing `</body>`:
```html
<script>
  window.CHAT_WIDGET_CONFIG = {
    appName: "Synthetic Population Engine",
    systemPrompt: "You are a helpful assistant for the Synthetic Population Engine. This tool generates statistically realistic AI individuals from census data and polls them on questions. Help the user understand poll results, population demographics, and backtesting features.",
    contextFn: () => {
      return `Population: ${document.getElementById('stat-profiles')?.textContent || '?'} profiles, ${document.getElementById('stat-archetypes')?.textContent || '?'} archetypes. Current view: ${currentView}.`;
    },
    welcomeMessage: "Ask me about your synthetic population, poll results, or how backtesting works.",
    position: "bottom-right",
  };
</script>
<script src="/_skills/llm-chat-widget/dist/chat-widget.js"></script>
```

- [ ] **Step 2: Verify widget appears**

- [ ] **Step 3: Commit**

```bash
git commit -m "feat: chat widget integration with population context"
```

---

## Task 16: Quick Start Shortcut

**Files:**
- Create: `quick_starts/synthetic-population_start.bat`

- [ ] **Step 1: Create quick start**

```bat
@echo off
cd /d "%~dp0\..\apps\synthetic-population"
call start.bat
```

- [ ] **Step 2: Commit**

```bash
git commit -m "feat: quick start shortcut for synthetic population"
```

---

## Task 17: Full Test Suite Run + Final Validation

- [ ] **Step 1: Run full test suite**

Run: `cd apps/synthetic-population && python -m pytest tests/ -v --tb=short`
Expected: All tests PASS (existing 270 + new API/snapshot tests)

- [ ] **Step 2: Verify project structure matches spec**

Check all files from the file structure section exist.

- [ ] **Step 3: Manual browser test**

1. Open http://localhost:5000
2. Verify sidebar shows correct stats
3. Poll view: verify snapshot dropdown populates
4. Population view: verify table loads, filters work, detail panel opens
5. Backtest view: create a snapshot, verify it appears in list
6. Events view: create an event, preview drift, apply
7. Chat widget appears and responds

- [ ] **Step 4: Update TODO.md**

- [ ] **Step 5: Final commit**

```bash
git commit -m "feat: synthetic population web UI complete"
```
