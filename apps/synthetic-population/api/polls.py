import json
import sys
from datetime import datetime
from pathlib import Path
from flask import Blueprint, jsonify, request, current_app

polls_bp = Blueprint("polls", __name__)


def _data_dir() -> Path:
    return Path(current_app.config["DATA_DIR"])


def _polls_dir() -> Path:
    d = _data_dir() / "polls"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_registry() -> list:
    p = _data_dir() / "profiles" / "registry.json"
    if not p.exists():
        return []
    return json.loads(p.read_text())


def _load_profiles_for_snapshot(snapshot_id: str) -> tuple[list, str | None]:
    """Return (profiles, events_applied_through). Uses live registry or snapshot."""
    if snapshot_id == "live":
        profiles = _load_registry()
        return profiles, None

    data_dir = _data_dir()
    # Import here to avoid circular issues and to stay consistent with other blueprints
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from snapshots.manager import SnapshotManager
    manager = SnapshotManager(
        snapshots_dir=data_dir / "snapshots",
        registry_path=data_dir / "profiles" / "registry.json",
    )
    meta = manager.get_metadata(snapshot_id)
    filter_date = meta.get("date")
    profiles = manager.load(snapshot_id, filter_drift_after=filter_date)
    events_applied_through = meta.get("events_applied_through")
    return profiles, events_applied_through


def _build_archetypes(profiles: list) -> tuple[list, dict]:
    """
    Run ArchetypeBuilder on profiles, return (profiles_with_archetypes, weights).
    profiles_with_archetypes is a list of dicts (with archetype_id set).
    weights is {archetype_id: float}.
    """
    import pandas as pd
    from generator.archetypes import ArchetypeBuilder

    if not profiles:
        return [], {}

    df = pd.DataFrame(profiles)
    builder = ArchetypeBuilder(min_cell_size=1)
    df_out = builder.build(df)
    weights = builder.get_weights()

    # Merge archetype_id back into profile dicts
    profiles_out = df_out.to_dict(orient="records")
    # The original profiles may have had archetype_id; overwrite with freshly built one
    return profiles_out, weights


# ---------------------------------------------------------------------------
# POST /api/polls — create a new poll
# ---------------------------------------------------------------------------

def _get_opinion(question: str, profile: dict) -> tuple | None:
    """Get opinion from bottom-up CES engine. Returns None if question not covered."""
    engine = current_app.config.get("OPINION_ENGINE")
    if engine is None:
        return None
    world_shifts = _get_active_world_shifts()
    return engine.get_opinion(question, profile, world_shifts=world_shifts)


def _get_active_world_shifts() -> dict:
    """Load aggregated opinion shifts from active world updates."""
    try:
        data_dir = _data_dir()
        wu_path = data_dir / "world_updates.json"
        if not wu_path.exists():
            return {}
        updates = json.loads(wu_path.read_text())
        combined = {"dem": 0.0, "rep": 0.0, "independent": 0.0}
        for u in updates:
            if not u.get("active", True):
                continue
            for party, shift in u.get("shifts", {}).items():
                combined[party] = combined.get(party, 0.0) + shift
        for k in combined:
            combined[k] = max(-0.15, min(0.15, combined[k]))
        return combined
    except Exception:
        return {}


def _apply_filters(profiles: list, filters: dict) -> list:
    """Filter profiles by demographic criteria.

    filters is a dict like {"state": "TX", "party_id": "rep", "race": "white"}.
    Keys with empty/null values are ignored.
    party_id supports prefix matching: "dem" matches strong_dem, dem, lean_dem.
    """
    if not filters:
        return profiles

    filtered = profiles
    for key, value in filters.items():
        if not value:
            continue
        # Party supports prefix groups
        if key == "party_id":
            if value == "dem":
                filtered = [p for p in filtered if p.get("party_id", "") in ("strong_dem", "dem", "lean_dem")]
            elif value == "rep":
                filtered = [p for p in filtered if p.get("party_id", "") in ("strong_rep", "rep", "lean_rep")]
            else:
                filtered = [p for p in filtered if p.get(key) == value]
        elif key == "age_bracket":
            filtered = [p for p in filtered if p.get("age_bracket") == value]
        else:
            filtered = [p for p in filtered if p.get(key) == value]
    return filtered


@polls_bp.route("/api/polls", methods=["POST"])
def create_poll():
    body = request.get_json(force=True, silent=True) or {}
    question = body.get("question", "").strip()
    snapshot_id = body.get("snapshot_id", "live")
    filters = body.get("filters", {}) or {}

    if not question:
        return jsonify({"error": "question is required"}), 400

    # Reject negated question stems — the engine answers support/approval
    # distributions and would silently invert them (audit H2).
    from engine.ces_columns import detect_negated_phrasing, NEGATED_PHRASING_ERROR
    if detect_negated_phrasing(question):
        return jsonify({"error": NEGATED_PHRASING_ERROR}), 400

    # Load profiles
    try:
        profiles, events_applied_through = _load_profiles_for_snapshot(snapshot_id)
    except KeyError as e:
        return jsonify({"error": str(e)}), 404

    if not profiles:
        return jsonify({"error": "No profiles found"}), 400

    # Apply demographic filters
    profiles = _apply_filters(profiles, filters)

    if not profiles:
        return jsonify({"error": f"No profiles match filters: {filters}"}), 400

    # Build archetypes from filtered profiles
    profiles_with_archetypes, weights = _build_archetypes(profiles)

    if not weights:
        return jsonify({"error": "Could not build archetypes from profiles"}), 400

    # Prepare poll via PollRunner
    from engine.poll import PollRunner
    polls_dir = _polls_dir()
    runner = PollRunner(polls_dir=str(polls_dir))
    poll_id = runner.prepare(question, profiles_with_archetypes, weights)

    # Save structured prompts JSON
    poll_dir = polls_dir / poll_id
    poll_dir.mkdir(parents=True, exist_ok=True)

    prompts_list = [
        {
            "archetype_id": aid,
            "prompt_text": runner.prompts[aid],
            "weight": weights.get(aid, 0),
        }
        for aid in sorted(runner.prompts.keys())
    ]
    (poll_dir / "prompts.json").write_text(json.dumps(prompts_list, indent=2))

    # Save metadata
    created_at = datetime.now().isoformat()
    # Strip empty filter values before saving
    active_filters = {k: v for k, v in filters.items() if v}
    metadata = {
        "poll_id": poll_id,
        "question": question,
        "snapshot_id": snapshot_id,
        "filters": active_filters,
        "status": "pending",
        "created_at": created_at,
        "archetype_count": len(weights),
        "profile_count": len(profiles),
        "events_applied_through": events_applied_through,
        "responses_recorded": 0,
    }
    (poll_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))

    return jsonify({
        "poll_id": poll_id,
        "status": "pending",
        "archetype_count": len(weights),
        "profile_count": len(profiles),
    }), 201


# ---------------------------------------------------------------------------
# GET /api/polls — list all polls
# ---------------------------------------------------------------------------

@polls_bp.route("/api/polls", methods=["GET"])
def list_polls():
    polls_dir = _polls_dir()
    results = []
    for entry in sorted(polls_dir.iterdir()):
        if not entry.is_dir():
            continue
        meta_path = entry / "metadata.json"
        if not meta_path.exists():
            continue
        meta = json.loads(meta_path.read_text())

        # Pull distribution from results.json if complete
        distribution = None
        results_path = entry / "results.json"
        if results_path.exists():
            try:
                res = json.loads(results_path.read_text())
                distribution = res.get("distribution")
            except Exception:
                pass

        results.append({
            "poll_id": meta.get("poll_id"),
            "question": meta.get("question"),
            "date": meta.get("created_at"),
            "snapshot_id": meta.get("snapshot_id"),
            "status": meta.get("status"),
            "distribution": distribution,
            "filters": meta.get("filters", {}),
            "profile_count": meta.get("profile_count"),
        })
    return jsonify(results)


# ---------------------------------------------------------------------------
# GET /api/polls/<poll_id> — get poll detail
# ---------------------------------------------------------------------------

@polls_bp.route("/api/polls/<poll_id>", methods=["GET"])
def get_poll(poll_id):
    polls_dir = _polls_dir()
    poll_dir = polls_dir / poll_id
    meta_path = poll_dir / "metadata.json"

    if not meta_path.exists():
        return jsonify({"error": f"Poll '{poll_id}' not found"}), 404

    meta = json.loads(meta_path.read_text())

    # Count recorded responses
    responses_dir = poll_dir / "responses"
    meta["responses_recorded"] = len(list(responses_dir.glob("*.json"))) if responses_dir.exists() else 0

    # If complete, attach results
    results_path = poll_dir / "results.json"
    if meta.get("status") == "complete" and results_path.exists():
        results = json.loads(results_path.read_text())
        meta["distribution"] = results.get("distribution")
        meta["breakdowns"] = results.get("breakdowns")
        meta["mean_confidence"] = results.get("mean_confidence")
        meta["confidence_interval"] = results.get("confidence_interval")
        meta["n_responses"] = results.get("n_responses")
        meta["n_missing"] = results.get("n_missing")

    return jsonify(meta)


# ---------------------------------------------------------------------------
# POST /api/polls/<poll_id>/send-to-claude — mark poll for Claude processing
# ---------------------------------------------------------------------------

@polls_bp.route("/api/polls/<poll_id>/send-to-claude", methods=["POST"])
def send_to_claude(poll_id):
    polls_dir = _polls_dir()
    meta_path = polls_dir / poll_id / "metadata.json"

    if not meta_path.exists():
        return jsonify({"error": f"Poll '{poll_id}' not found"}), 404

    meta = json.loads(meta_path.read_text())
    meta["status"] = "awaiting_claude"
    meta_path.write_text(json.dumps(meta, indent=2))

    return jsonify({"status": "awaiting_claude", "poll_id": poll_id})


# ---------------------------------------------------------------------------
# GET /api/polls/queue — return polls awaiting Claude processing
# ---------------------------------------------------------------------------

@polls_bp.route("/api/polls/queue", methods=["GET"])
def get_poll_queue():
    polls_dir = _polls_dir()
    queue = []
    for entry in sorted(polls_dir.iterdir()):
        if not entry.is_dir():
            continue
        meta_path = entry / "metadata.json"
        if not meta_path.exists():
            continue
        meta = json.loads(meta_path.read_text())
        if meta.get("status") == "awaiting_claude":
            queue.append({
                "poll_id": meta["poll_id"],
                "question": meta.get("question"),
                "archetype_count": meta.get("archetype_count"),
                "created_at": meta.get("created_at"),
            })
    return jsonify(queue)


# ---------------------------------------------------------------------------
# POST /api/polls/<poll_id>/auto-complete — CES-modeled responses + aggregate
# ---------------------------------------------------------------------------

@polls_bp.route("/api/polls/<poll_id>/auto-complete", methods=["POST"])
def auto_complete_poll(poll_id):
    """Generate CES-modeled responses for all archetypes and aggregate.

    Uses real cross-tabulations from the 2024 Cooperative Election Study
    (60,000 respondents, Harvard Dataverse) to predict opinions by party_id
    and demographic profile. Responses reflect actual survey distributions.
    """
    polls_dir = _polls_dir()
    poll_dir = polls_dir / poll_id
    meta_path = poll_dir / "metadata.json"
    prompts_path = poll_dir / "prompts.json"

    if not meta_path.exists():
        return jsonify({"error": f"Poll '{poll_id}' not found"}), 404

    meta = json.loads(meta_path.read_text())
    if meta.get("status") == "complete":
        return jsonify({"error": "Poll already complete"}), 400

    if not prompts_path.exists():
        return jsonify({"error": "No prompts found for this poll"}), 400

    prompts = json.loads(prompts_path.read_text())
    question = meta.get("question", "")
    snapshot_id = meta.get("snapshot_id", "live")
    filters = meta.get("filters", {})

    # Check CES coverage before doing any work
    from engine.ces_columns import match_question
    if match_question(question) is None:
        return jsonify({
            "error": "No CES survey data covers this question. Covered topics: approval, economy, immigration, healthcare, environment, fiscal policy, education.",
        }), 400

    # Load profiles to get demographics per archetype
    try:
        profiles, _ = _load_profiles_for_snapshot(snapshot_id)
    except Exception:
        profiles = _load_registry()

    # Apply same filters used at poll creation
    if filters:
        profiles = _apply_filters(profiles, filters)

    # Rebuild archetypes EXACTLY as at poll creation and index representative
    # profiles by the FRESH assignment. The archetype_id stored in the
    # registry comes from the original population build and does NOT agree
    # with the fresh IDs the prompts/weights are keyed by — indexing by the
    # stale stored IDs silently polled wrong-party or empty profiles
    # (audit H1).
    profiles_with_arch, _ = _build_archetypes(profiles)

    profiles_by_arch = {}
    for p in profiles_with_arch:
        aid = p.get("archetype_id")
        if aid and aid not in profiles_by_arch:
            profiles_by_arch[aid] = p

    # Generate CES-modeled responses
    responses_dir = poll_dir / "responses"
    responses_dir.mkdir(exist_ok=True)
    recorded = 0

    for prompt_entry in prompts:
        aid = prompt_entry["archetype_id"]
        profile = profiles_by_arch.get(aid)
        if not profile:
            # No representative for this archetype id — never poll an empty
            # {} profile (it would KNN-match an arbitrary corner of CES).
            continue

        opinion_result = _get_opinion(question, profile)
        if opinion_result is None:
            continue
        opinion, confidence, reasoning = opinion_result

        result = {
            "archetype_id": aid,
            "response": opinion,
            "confidence": confidence,
            "response_text": reasoning,
            "hedge_score": 0.1,
            "flags": [],
            "demographics": {
                k: profile.get(k)
                for k in ["party_id", "race", "education", "urban_rural", "age_bracket"]
                if profile.get(k)
            },
            "source": "ces_microdata",
        }

        (responses_dir / f"{aid}.json").write_text(json.dumps(result, indent=2))
        recorded += 1

    # Auto-aggregate
    responses = []
    for resp_file in responses_dir.glob("*.json"):
        try:
            responses.append(json.loads(resp_file.read_text()))
        except Exception:
            continue

    weights = {e["archetype_id"]: e["weight"] for e in prompts}

    from engine.aggregate import PollAggregator
    agg = PollAggregator(weights)
    agg_result = agg.aggregate(responses)
    agg_result["poll_id"] = poll_id
    agg_result["question"] = meta.get("question")
    agg_result["response_source"] = "ces_modeled"

    (poll_dir / "results.json").write_text(json.dumps(agg_result, indent=2, default=str))

    meta["status"] = "complete"
    meta["response_source"] = "ces_modeled"
    meta_path.write_text(json.dumps(meta, indent=2))

    return jsonify({
        "recorded": recorded,
        "status": "complete",
        "distribution": agg_result.get("distribution"),
    })



# Old _ces_modeled_opinion function removed — replaced by engine/opinion.py
# which uses real CES microdata KNN matching instead of hardcoded curves.


# ---------------------------------------------------------------------------
# DELETE /api/polls/<poll_id> — delete a poll
# ---------------------------------------------------------------------------

@polls_bp.route("/api/polls/<poll_id>", methods=["DELETE"])
def delete_poll(poll_id):
    import shutil
    polls_dir = _polls_dir()
    poll_dir = polls_dir / poll_id

    if not poll_dir.exists():
        return jsonify({"error": f"Poll '{poll_id}' not found"}), 404

    shutil.rmtree(poll_dir)
    return jsonify({"deleted": True})


# ---------------------------------------------------------------------------
# GET /api/polls/<poll_id>/prompts — get prompt batch
# ---------------------------------------------------------------------------

@polls_bp.route("/api/polls/<poll_id>/prompts", methods=["GET"])
def get_poll_prompts(poll_id):
    polls_dir = _polls_dir()
    prompts_path = polls_dir / poll_id / "prompts.json"

    if not prompts_path.exists():
        return jsonify({"error": f"Poll '{poll_id}' not found"}), 404

    prompts = json.loads(prompts_path.read_text())
    return jsonify(prompts)


# ---------------------------------------------------------------------------
# POST /api/polls/<poll_id>/responses — record a single response
# ---------------------------------------------------------------------------

@polls_bp.route("/api/polls/<poll_id>/responses", methods=["POST"])
def record_response(poll_id):
    polls_dir = _polls_dir()
    poll_dir = polls_dir / poll_id
    meta_path = poll_dir / "metadata.json"

    if not meta_path.exists():
        return jsonify({"error": f"Poll '{poll_id}' not found"}), 404

    body = request.get_json(force=True, silent=True) or {}
    archetype_id = body.get("archetype_id", "").strip()
    response_text = body.get("response_text", "")
    opinion = body.get("opinion", "unsure")
    confidence = body.get("confidence", 5)

    if not archetype_id:
        return jsonify({"error": "archetype_id is required"}), 400

    # Load the matching profile from prompts.json to get drift_log for integrity check
    prompts_path = poll_dir / "prompts.json"
    profile = {}
    if prompts_path.exists():
        # We need the profile for check_consistency — reload from registry/snapshot
        meta = json.loads(meta_path.read_text())
        snapshot_id = meta.get("snapshot_id", "live")
        try:
            profiles, _ = _load_profiles_for_snapshot(snapshot_id)
            for p in profiles:
                if p.get("archetype_id") == archetype_id:
                    profile = p
                    break
        except Exception:
            pass

    from engine.integrity import check_hedge_score, check_consistency
    hedge_score = check_hedge_score(response_text)
    meta = json.loads(meta_path.read_text())
    drift_log = profile.get("drift_log", [])
    new_response_entry = {
        "topic": meta.get("question", ""),
        "position": opinion,
        "confidence": confidence,
    }
    flags = check_consistency(drift_log, new_response_entry)

    result = {
        "archetype_id": archetype_id,
        "response": opinion,
        "confidence": confidence,
        "response_text": response_text,
        "hedge_score": hedge_score,
        "flags": flags,
        "demographics": {
            k: profile.get(k)
            for k in ["party_id", "race", "education", "urban_rural"]
            if profile.get(k)
        },
    }

    # Save as individual JSON file in responses/
    responses_dir = poll_dir / "responses"
    responses_dir.mkdir(exist_ok=True)
    response_file = responses_dir / f"{archetype_id}.json"
    response_file.write_text(json.dumps(result, indent=2))

    return jsonify(result), 201


# ---------------------------------------------------------------------------
# POST /api/polls/<poll_id>/aggregate — run aggregation
# ---------------------------------------------------------------------------

@polls_bp.route("/api/polls/<poll_id>/aggregate", methods=["POST"])
def aggregate_poll(poll_id):
    polls_dir = _polls_dir()
    poll_dir = polls_dir / poll_id
    meta_path = poll_dir / "metadata.json"

    if not meta_path.exists():
        return jsonify({"error": f"Poll '{poll_id}' not found"}), 404

    meta = json.loads(meta_path.read_text())

    # Load all saved responses
    responses_dir = poll_dir / "responses"
    responses = []
    if responses_dir.exists():
        for resp_file in responses_dir.glob("*.json"):
            try:
                responses.append(json.loads(resp_file.read_text()))
            except Exception:
                continue

    if not responses:
        return jsonify({"error": "No responses recorded for this poll"}), 400

    # Reconstruct weights from the saved prompts list
    prompts_path = poll_dir / "prompts.json"
    weights = {}
    if prompts_path.exists():
        prompts_list = json.loads(prompts_path.read_text())
        for entry in prompts_list:
            weights[entry["archetype_id"]] = entry["weight"]

    from engine.aggregate import PollAggregator
    agg = PollAggregator(weights)
    result = agg.aggregate(responses)
    result["poll_id"] = poll_id
    result["question"] = meta.get("question")

    # Save results
    (poll_dir / "results.json").write_text(json.dumps(result, indent=2, default=str))

    # Update metadata status
    meta["status"] = "complete"
    meta_path.write_text(json.dumps(meta, indent=2))

    return jsonify(result)
