import copy
import json
from pathlib import Path

from flask import Blueprint, jsonify, request, current_app

from monitor.events import EventStore
from monitor.drift import DriftEngine

events_bp = Blueprint("events", __name__)


def _get_store() -> EventStore:
    data_dir = Path(current_app.config["DATA_DIR"])
    return EventStore(data_dir / "events")


def _load_registry() -> list:
    data_dir = Path(current_app.config["DATA_DIR"])
    registry_path = data_dir / "profiles" / "registry.json"
    if not registry_path.exists():
        return []
    return json.loads(registry_path.read_text())


def _save_registry(profiles: list) -> None:
    data_dir = Path(current_app.config["DATA_DIR"])
    registry_path = data_dir / "profiles" / "registry.json"
    registry_path.write_text(json.dumps(profiles, indent=2))


@events_bp.route("/api/events", methods=["GET"])
def list_events():
    store = _get_store()
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    events = store.list(start_date=start_date, end_date=end_date)
    return jsonify(events)


@events_bp.route("/api/events", methods=["POST"])
def create_event():
    body = request.get_json(silent=True) or {}

    missing = [f for f in ("date", "description", "affected_segments") if f not in body]
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400

    store = _get_store()
    try:
        event_id = store.add(body)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({"event_id": event_id}), 201


@events_bp.route("/api/events/<event_id>/apply", methods=["POST"])
def apply_event(event_id):
    store = _get_store()

    try:
        event = store.get(event_id)
    except KeyError:
        return jsonify({"error": f"Event '{event_id}' not found"}), 404

    profiles = _load_registry()
    updated_profiles = DriftEngine.apply_batch(profiles, event)

    _save_registry(updated_profiles)

    # Mark event as applied
    event["applied"] = True
    data_dir = Path(current_app.config["DATA_DIR"])
    event_path = data_dir / "events" / f"{event_id}.json"
    event_path.write_text(json.dumps(event, indent=2))

    return jsonify({"profiles_affected": len(updated_profiles)})


@events_bp.route("/api/events/<event_id>/preview", methods=["GET"])
def preview_event(event_id):
    store = _get_store()

    try:
        event = store.get(event_id)
    except KeyError:
        return jsonify({"error": f"Event '{event_id}' not found"}), 404

    profiles = _load_registry()
    profiles_copy = copy.deepcopy(profiles)
    updated_profiles = DriftEngine.apply_batch(profiles_copy, event)

    changes = []
    affected_count = 0
    for original, updated in zip(profiles, updated_profiles):
        profile_changes = {}
        for key in updated:
            if key == "drift_log":
                continue
            if original.get(key) != updated.get(key):
                profile_changes[key] = {
                    "before": original.get(key),
                    "after": updated.get(key),
                }
        if profile_changes:
            affected_count += 1
            changes.append({
                "profile_id": updated.get("profile_id"),
                "changes": profile_changes,
            })

    return jsonify({"profiles_affected": affected_count, "changes": changes})
