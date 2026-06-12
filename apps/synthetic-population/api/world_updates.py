"""World Updates API — auto-fetch real public news to shift poll responses.

Fetches current headlines from public RSS feeds (AP, NPR, BBC, Reuters),
detects topics and sentiment direction, and computes per-party opinion shifts
that get applied to CES-modeled poll responses.
"""

import json
from datetime import datetime
from pathlib import Path

from flask import Blueprint, jsonify, request, current_app

from engine.news_fetch import (
    fetch_headlines as _fetch_headlines,
    sample_relevant as _sample_relevant,
    strip_html as _strip_html,
)
from engine.news_scoring import (
    detect_topics as _detect_topics,
    detect_direction as _detect_direction,
    compute_party_shift as _compute_opinion_shift,
)

world_updates_bp = Blueprint("world_updates", __name__)


def _updates_path() -> Path:
    p = Path(current_app.config["DATA_DIR"]) / "world_updates.json"
    if not p.exists():
        p.write_text("[]")
    return p


def _load_updates() -> list:
    return json.loads(_updates_path().read_text())


def _save_updates(updates: list):
    _updates_path().write_text(json.dumps(updates, indent=2))


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@world_updates_bp.route("/api/world-updates", methods=["GET"])
def list_updates():
    return jsonify(_load_updates())


@world_updates_bp.route("/api/world-updates", methods=["POST"])
def create_update():
    """Create a single world update from provided text."""
    body = request.get_json(force=True, silent=True) or {}
    text = body.get("text", "").strip()
    if not text:
        return jsonify({"error": "text is required"}), 400

    topics = _detect_topics(text)
    direction = _detect_direction(text)
    shifts = _compute_opinion_shift(topics, direction)

    update = {
        "id": f"WU-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "text": text,
        "date": body.get("date", datetime.now().strftime("%Y-%m-%d")),
        "created_at": datetime.now().isoformat(),
        "topics": topics,
        "direction": direction,
        "shifts": shifts,
        "active": True,
        "source": "manual",
    }

    updates = _load_updates()
    updates.insert(0, update)
    _save_updates(updates)

    return jsonify(update), 201


@world_updates_bp.route("/api/world-updates/fetch", methods=["POST"])
def fetch_updates():
    """Auto-fetch current headlines from public RSS feeds, detect topics, create updates.

    This simulates the population 'browsing the web' — sampling a handful
    of real headlines that real people would encounter in their news feeds.
    """
    # Clear previous auto-fetched items (keep manual ones)
    updates = _load_updates()
    updates = [u for u in updates if u.get("source") != "auto"]

    # Fetch live headlines
    headlines = _fetch_headlines(max_per_feed=10)
    if not headlines:
        return jsonify({"error": "Could not fetch any headlines. Check internet connection."}), 502

    # Sample what a typical person would actually see/read
    sampled = _sample_relevant(headlines, n=8)

    new_updates = []
    for i, h in enumerate(sampled):
        text = h["title"]
        if h.get("description"):
            text += ". " + h["description"]

        topics = _detect_topics(text)
        direction = _detect_direction(text)
        shifts = _compute_opinion_shift(topics, direction)

        update = {
            "id": f"WU-{datetime.now().strftime('%Y%m%d%H%M%S')}-{i:02d}",
            "text": h["title"],
            "description": h.get("description", ""),
            "date": datetime.now().strftime("%Y-%m-%d"),
            "created_at": datetime.now().isoformat(),
            "topics": topics,
            "direction": direction,
            "shifts": shifts,
            "active": True,
            "source": "auto",
            "feed": h.get("feed", ""),
        }
        new_updates.append(update)

    # Prepend new auto-fetched updates
    updates = new_updates + updates
    _save_updates(updates)

    return jsonify({
        "fetched": len(new_updates),
        "headlines_scanned": len(headlines),
        "updates": new_updates,
    })


@world_updates_bp.route("/api/world-updates/<update_id>", methods=["DELETE"])
def delete_update(update_id):
    updates = _load_updates()
    updates = [u for u in updates if u["id"] != update_id]
    _save_updates(updates)
    return jsonify({"deleted": True})


@world_updates_bp.route("/api/world-updates/<update_id>/toggle", methods=["POST"])
def toggle_update(update_id):
    updates = _load_updates()
    for u in updates:
        if u["id"] == update_id:
            u["active"] = not u.get("active", True)
            _save_updates(updates)
            return jsonify(u)
    return jsonify({"error": "Not found"}), 404


@world_updates_bp.route("/api/world-updates/active-shifts", methods=["GET"])
def get_active_shifts():
    updates = _load_updates()
    combined = {"dem": 0.0, "rep": 0.0, "independent": 0.0}
    active_count = 0
    for u in updates:
        if not u.get("active", True):
            continue
        active_count += 1
        for party, shift in u.get("shifts", {}).items():
            combined[party] = combined.get(party, 0.0) + shift

    for k in combined:
        combined[k] = max(-0.15, min(0.15, combined[k]))

    return jsonify({"shifts": combined, "active_count": active_count})


@world_updates_bp.route("/api/world-updates/clear-auto", methods=["POST"])
def clear_auto():
    """Remove all auto-fetched updates, keep manual ones."""
    updates = _load_updates()
    updates = [u for u in updates if u.get("source") != "auto"]
    _save_updates(updates)
    return jsonify({"remaining": len(updates)})


@world_updates_bp.route("/api/world-updates/cycle", methods=["POST"])
def run_update_cycle():
    """Run the full update cycle: fetch → score → apply beliefs → calibrate."""
    from engine.update_cycle import run_cycle
    engine = current_app.config.get("OPINION_ENGINE")
    data_dir = Path(current_app.config["DATA_DIR"])
    try:
        summary = run_cycle(data_dir, engine)
    except Exception as e:
        return jsonify({"error": f"Cycle failed: {e}"}), 500
    return jsonify(summary)


@world_updates_bp.route("/api/world-updates/belief-history", methods=["GET"])
def belief_history():
    p = Path(current_app.config["DATA_DIR"]) / "belief_history.json"
    try:
        return jsonify(json.loads(p.read_text()) if p.exists() else [])
    except (json.JSONDecodeError, OSError):
        return jsonify([])


@world_updates_bp.route("/api/world-updates/calibration-status", methods=["GET"])
def calibration_status():
    p = Path(current_app.config["DATA_DIR"]) / "calibration_history.json"
    try:
        history = json.loads(p.read_text()) if p.exists() else []
    except (json.JSONDecodeError, OSError):
        history = []
    return jsonify(history[-1] if history else {"verdict": "none"})
