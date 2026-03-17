from flask import Blueprint, jsonify, current_app
from pathlib import Path
import json

stats_bp = Blueprint("stats", __name__)


def _load_registry(data_dir: Path) -> list:
    registry_path = data_dir / "profiles" / "registry.json"
    if not registry_path.exists():
        return []
    with open(registry_path, "r") as f:
        return json.load(f)


def _count_polls(data_dir: Path) -> int:
    polls_dir = data_dir / "polls"
    if not polls_dir.exists():
        return 0
    return sum(1 for p in polls_dir.iterdir() if p.is_dir() and p.name.startswith("POLL-"))


def _last_event_date(data_dir: Path):
    events_dir = data_dir / "events"
    if not events_dir.exists():
        return None
    event_files = sorted(events_dir.glob("*.json"))
    if not event_files:
        return None
    with open(event_files[-1], "r") as f:
        event = json.load(f)
    return event.get("date") or event.get("event_date")


def _demographic_summary(profiles: list) -> dict:
    if not profiles:
        return {}

    dimensions = ["sex", "race", "education", "party_id"]
    summary = {}

    for dim in dimensions:
        counts = {}
        total = 0
        for p in profiles:
            val = p.get(dim)
            if val is not None:
                counts[val] = counts.get(val, 0) + 1
                total += 1
        if total > 0:
            summary[dim] = {k: round(v / total, 4) for k, v in counts.items()}
        else:
            summary[dim] = {}

    return summary


@stats_bp.route("/api/stats", methods=["GET"])
def get_stats():
    data_dir = Path(current_app.config["DATA_DIR"])
    profiles = _load_registry(data_dir)

    archetype_ids = {p.get("archetype_id") for p in profiles if p.get("archetype_id")}

    return jsonify({
        "profile_count": len(profiles),
        "archetype_count": len(archetype_ids),
        "polls_run": _count_polls(data_dir),
        "last_event_date": _last_event_date(data_dir),
        "demographic_summary": _demographic_summary(profiles),
    })
