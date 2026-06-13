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

@polls_bp.route("/api/polls", methods=["POST"])
def create_poll():
    body = request.get_json(force=True, silent=True) or {}
    question = body.get("question", "").strip()
    snapshot_id = body.get("snapshot_id", "live")

    if not question:
        return jsonify({"error": "question is required"}), 400

    # Load profiles
    try:
        profiles, events_applied_through = _load_profiles_for_snapshot(snapshot_id)
    except KeyError as e:
        return jsonify({"error": str(e)}), 404

    if not profiles:
        return jsonify({"error": "No profiles found"}), 400

    # Build archetypes from profiles
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
    metadata = {
        "poll_id": poll_id,
        "question": question,
        "snapshot_id": snapshot_id,
        "status": "pending",
        "created_at": created_at,
        "archetype_count": len(weights),
        "events_applied_through": events_applied_through,
        "responses_recorded": 0,
    }
    (poll_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))

    return jsonify({"poll_id": poll_id, "status": "pending"}), 201


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

        # Try to pull headline_result from results.json if complete
        headline_result = None
        results_path = entry / "results.json"
        if results_path.exists():
            try:
                res = json.loads(results_path.read_text())
                dist = res.get("distribution", {})
                if dist:
                    headline_result = max(dist, key=dist.get)
            except Exception:
                pass

        results.append({
            "poll_id": meta.get("poll_id"),
            "question": meta.get("question"),
            "date": meta.get("created_at"),
            "snapshot_id": meta.get("snapshot_id"),
            "status": meta.get("status"),
            "headline_result": headline_result,
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
# POST /api/polls/<poll_id>/auto-complete — heuristic responses + aggregate
# ---------------------------------------------------------------------------

@polls_bp.route("/api/polls/<poll_id>/auto-complete", methods=["POST"])
def auto_complete_poll(poll_id):
    """Generate heuristic responses for all archetypes and aggregate.

    NOT Claude responses — these are rule-based opinions derived from each
    archetype's demographics (party, education, age, religion). Use as a
    baseline or for testing until Claude-in-Chrome automation is wired up.
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
    question = meta.get("question", "").lower()
    snapshot_id = meta.get("snapshot_id", "live")

    # Load profiles to get demographics per archetype
    try:
        profiles, _ = _load_profiles_for_snapshot(snapshot_id)
    except Exception:
        profiles = _load_registry()

    # Index profiles by archetype_id
    profiles_by_arch = {}
    for p in profiles:
        aid = p.get("archetype_id")
        if aid and aid not in profiles_by_arch:
            profiles_by_arch[aid] = p

    # Generate heuristic responses
    responses_dir = poll_dir / "responses"
    responses_dir.mkdir(exist_ok=True)
    recorded = 0

    for prompt_entry in prompts:
        aid = prompt_entry["archetype_id"]
        profile = profiles_by_arch.get(aid, {})

        opinion, confidence, reasoning = _heuristic_opinion(question, profile)

        result = {
            "archetype_id": aid,
            "response": opinion,
            "confidence": confidence,
            "response_text": reasoning,
            "hedge_score": 0.1,  # heuristic responses don't hedge
            "flags": [],
            "demographics": {
                k: profile.get(k)
                for k in ["party_id", "race", "education", "urban_rural", "age_bracket"]
                if profile.get(k)
            },
            "source": "heuristic",  # clearly marked as non-Claude
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
    agg_result["response_source"] = "heuristic"

    (poll_dir / "results.json").write_text(json.dumps(agg_result, indent=2, default=str))

    meta["status"] = "complete"
    meta["response_source"] = "heuristic"
    meta_path.write_text(json.dumps(meta, indent=2))

    return jsonify({
        "recorded": recorded,
        "status": "complete",
        "distribution": agg_result.get("distribution"),
    })


def _heuristic_opinion(question: str, profile: dict) -> tuple:
    """Generate a demographically-informed opinion for a question.

    Returns (opinion, confidence, reasoning).
    """
    import random
    party = profile.get("party_id", "independent")
    edu = profile.get("education", "")
    age_bracket = profile.get("age_bracket", "35-44")
    race = profile.get("race", "")
    religion = profile.get("religion_affiliation", "")
    urban = profile.get("urban_rural", "")

    # Detect question topic signals
    q = question.lower()
    is_progressive_topic = any(w in q for w in [
        "climate", "environment", "gun control", "universal health", "minimum wage",
        "student loan", "abortion rights", "marijuana", "immigration reform",
        "social security expand", "renewable", "tax the rich", "wealth tax",
    ])
    is_conservative_topic = any(w in q for w in [
        "border wall", "tax cut", "deregulat", "military spend", "gun rights",
        "school choice", "tough on crime", "death penalty", "abortion ban",
        "oil", "drill", "tariff", "trade war",
    ])
    is_economic = any(w in q for w in [
        "inflation", "economy", "recession", "interest rate", "fed ", "gdp",
        "unemployment", "jobs", "wages", "stock market", "housing",
    ])
    is_social = any(w in q for w in [
        "marriage", "transgender", "religion", "prayer", "church",
        "family values", "traditional",
    ])

    # Base lean from party
    dem_lean = party in ("strong_dem", "dem", "lean_dem")
    rep_lean = party in ("strong_rep", "rep", "lean_rep")
    strong = party.startswith("strong_")

    # Compute opinion probability
    if is_progressive_topic:
        yes_prob = 0.75 if dem_lean else (0.20 if rep_lean else 0.45)
    elif is_conservative_topic:
        yes_prob = 0.20 if dem_lean else (0.75 if rep_lean else 0.45)
    elif is_economic:
        # Economic questions — more nuanced, education matters
        if edu in ("graduate", "bachelors"):
            yes_prob = 0.55  # educated lean optimistic
        else:
            yes_prob = 0.40  # less educated more pessimistic
        # Party tilt
        if rep_lean:
            yes_prob -= 0.10  # conservatives more skeptical of gov econ
        elif dem_lean:
            yes_prob += 0.05
    elif is_social:
        if religion in ("evangelical",) and rep_lean:
            yes_prob = 0.25  # conservative on social issues
        elif religion == "none" and dem_lean:
            yes_prob = 0.75
        else:
            yes_prob = 0.45
    else:
        # Generic question — slight party lean
        yes_prob = 0.55 if dem_lean else (0.40 if rep_lean else 0.48)

    # Age modifier: older people slightly more conservative
    if age_bracket in ("65+", "55-64"):
        yes_prob -= 0.05
    elif age_bracket in ("18-24", "25-34"):
        yes_prob += 0.05

    # Urban modifier
    if urban == "rural":
        yes_prob -= 0.05
    elif urban == "urban":
        yes_prob += 0.03

    # Clamp
    yes_prob = max(0.05, min(0.95, yes_prob))

    # Decide
    roll = random.random()
    if roll < yes_prob:
        opinion = "yes"
    elif roll < yes_prob + (1 - yes_prob) * 0.7:
        opinion = "no"
    else:
        opinion = "unsure"

    # Confidence: strong partisans are more confident
    base_conf = 7 if strong else (5 if party != "independent" else 4)
    confidence = max(1, min(10, base_conf + random.randint(-2, 2)))

    # Brief reasoning
    party_label = {"strong_dem": "strong Democrat", "dem": "Democrat", "lean_dem": "lean Democrat",
                   "independent": "independent", "lean_rep": "lean Republican",
                   "rep": "Republican", "strong_rep": "strong Republican"}.get(party, party)
    reasoning = f"As a {party_label} from a {urban or 'mixed'} area with {edu or 'some'} education, this person {opinion}s. [heuristic response]"

    return opinion, confidence, reasoning


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
