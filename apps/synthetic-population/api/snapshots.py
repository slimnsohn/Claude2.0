from flask import Blueprint, jsonify, request, current_app
from pathlib import Path
from snapshots.manager import SnapshotManager

snapshots_bp = Blueprint("snapshots", __name__)


def _get_manager() -> SnapshotManager:
    data_dir = Path(current_app.config["DATA_DIR"])
    return SnapshotManager(
        snapshots_dir=data_dir / "snapshots",
        registry_path=data_dir / "profiles" / "registry.json",
    )


@snapshots_bp.route("/api/snapshots", methods=["POST"])
def create_snapshot():
    body = request.get_json(force=True, silent=True) or {}
    date = body.get("date")
    label = body.get("label")
    if not date or not label:
        return jsonify({"error": "date and label are required"}), 400
    manager = _get_manager()
    snapshot_id = manager.create(date=date, label=label)
    return jsonify({"snapshot_id": snapshot_id}), 201


@snapshots_bp.route("/api/snapshots", methods=["GET"])
def list_snapshots():
    manager = _get_manager()
    snapshots = manager.list_snapshots()
    result = [
        {
            "snapshot_id": s["snapshot_id"],
            "date": s["date"],
            "label": s["label"],
            "profile_count": s["profile_count"],
            "events_applied_through": s["events_applied_through"],
        }
        for s in snapshots
    ]
    return jsonify(result)


@snapshots_bp.route("/api/snapshots/<snapshot_id>", methods=["GET"])
def get_snapshot(snapshot_id):
    manager = _get_manager()
    try:
        meta = manager.get_metadata(snapshot_id)
    except KeyError:
        return jsonify({"error": f"Snapshot '{snapshot_id}' not found"}), 404
    return jsonify(meta)


@snapshots_bp.route("/api/snapshots/<snapshot_id>", methods=["DELETE"])
def delete_snapshot(snapshot_id):
    manager = _get_manager()
    try:
        manager.delete(snapshot_id)
    except KeyError:
        return jsonify({"error": f"Snapshot '{snapshot_id}' not found"}), 404
    return jsonify({"deleted": True})
