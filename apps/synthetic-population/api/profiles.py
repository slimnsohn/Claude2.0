import json
from pathlib import Path
from flask import Blueprint, jsonify, request, current_app

profiles_bp = Blueprint("profiles", __name__)


def _load_registry() -> list:
    data_dir = Path(current_app.config["DATA_DIR"])
    registry_path = data_dir / "profiles" / "registry.json"
    if not registry_path.exists():
        return []
    return json.loads(registry_path.read_text())


@profiles_bp.route("/api/profiles", methods=["GET"])
def list_profiles():
    profiles = _load_registry()

    # Apply filters
    sex = request.args.get("sex")
    race = request.args.get("race")
    education = request.args.get("education")
    party_id = request.args.get("party_id")
    state = request.args.get("state")
    urban_rural = request.args.get("urban_rural")
    archetype_id = request.args.get("archetype_id")
    search = request.args.get("search")

    if sex:
        profiles = [p for p in profiles if p.get("sex") == sex]
    if race:
        profiles = [p for p in profiles if p.get("race") == race]
    if education:
        profiles = [p for p in profiles if p.get("education") == education]
    if party_id:
        profiles = [p for p in profiles if p.get("party_id") == party_id]
    if state:
        profiles = [p for p in profiles if p.get("state") == state]
    if urban_rural:
        profiles = [p for p in profiles if p.get("urban_rural") == urban_rural]
    if archetype_id:
        profiles = [p for p in profiles if p.get("archetype_id") == archetype_id]
    if search:
        search_lower = search.lower()
        profiles = [p for p in profiles if search_lower in p.get("backstory", "").lower()]

    # Return summaries only (no backstory for performance)
    summary_keys = ("profile_id", "age", "sex", "race", "education", "state",
                    "party_id", "archetype_id", "urban_rural")
    summaries = [{k: p.get(k) for k in summary_keys} for p in profiles]

    return jsonify(summaries)


@profiles_bp.route("/api/profiles/<profile_id>", methods=["GET"])
def get_profile(profile_id):
    profiles = _load_registry()
    for profile in profiles:
        if profile.get("profile_id") == profile_id:
            return jsonify(profile)
    return jsonify({"error": f"Profile '{profile_id}' not found"}), 404
