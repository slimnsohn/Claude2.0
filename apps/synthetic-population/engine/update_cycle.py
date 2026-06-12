"""Full update cycle: fetch → score → decay → expose/update → persist → calibrate.

Flask-independent so both the API endpoint and the CLI can run it.
"""
import json
from datetime import datetime
from pathlib import Path

from engine.beliefs import update_population
from engine.calibration import run_calibration, synthetic_distribution
from engine.news_fetch import fetch_headlines, sample_relevant
from engine.news_scoring import compute_party_shift, score_events
from engine.registry_io import load_registry, save_registry

N_EVENTS_PER_CYCLE = 8


def _direction_label(direction: float) -> str:
    if direction > 0.1:
        return "positive"
    if direction < -0.1:
        return "negative"
    return "neutral"


def _events_to_updates(events: list, now: datetime, run_id: str) -> list:
    """World-updates entries: new scoring fields + legacy fields for UI/fallback compat."""
    updates = []
    for i, e in enumerate(events):
        label = _direction_label(e["direction"])
        updates.append({
            "id": f"WU-{now.strftime('%Y%m%d%H%M%S')}-{i:02d}",
            "text": e["text"],
            "description": e.get("description", ""),
            "date": now.strftime("%Y-%m-%d"),
            "created_at": now.isoformat(),
            "topics": e["topics"] or ["general"],
            "direction": label,
            "direction_score": e["direction"],
            "salience": e["salience"],
            "framing": e["framing"],
            "scoring_method": e["scoring_method"],
            "shifts": compute_party_shift(e["topics"] or ["general"], label),
            "active": True,
            "source": "auto",
            "feed": e.get("feed", ""),
            "cycle_id": run_id,
        })
    return updates


def run_cycle(data_dir, opinion_engine, fetch_fn=None, now: datetime = None) -> dict:
    data_dir = Path(data_dir)
    now = now or datetime.now()
    run_id = f"CY-{now.strftime('%Y%m%d%H%M%S')}"

    # 1. Fetch + sample headlines
    headlines = (fetch_fn or fetch_headlines)()
    sampled = sample_relevant(headlines, n=N_EVENTS_PER_CYCLE) if headlines else []

    # 2. Score
    events, method = score_events(sampled) if sampled else ([], "none")

    # 3. Persist world updates (replace previous auto entries, keep manual)
    wu_path = data_dir / "world_updates.json"
    existing = json.loads(wu_path.read_text()) if wu_path.exists() else []
    manual = [u for u in existing if u.get("source") != "auto"]
    wu_path.write_text(json.dumps(_events_to_updates(events, now, run_id) + manual, indent=2))

    # 4. Decay + apply to population
    profiles = load_registry(data_dir)
    summary = update_population(profiles, events, now, update_id=run_id)
    summary["scoring_method"] = method
    summary["headlines_scanned"] = len(headlines)

    # 5. Aggregate history row
    hist_path = data_dir / "belief_history.json"
    history = json.loads(hist_path.read_text()) if hist_path.exists() else []
    history.append({k: summary[k] for k in
                    ("update_id", "date", "n_events", "exposures", "mean_shift_by_topic")})
    hist_path.write_text(json.dumps(history[-365:], indent=2))

    # 6. Calibration gate (may dampen beliefs in place)
    if opinion_engine is not None and profiles:
        def poll_fn(question, profs):
            return synthetic_distribution(question, profs, opinion_engine)
        summary["calibration"] = run_calibration(
            data_dir, profiles, poll_fn, now=now, run_id=run_id)
    else:
        summary["calibration"] = {"verdict": "stale", "note": "no opinion engine"}

    # 7. Persist registry (post-decay, post-update, post-dampening)
    save_registry(data_dir, profiles)
    return summary
