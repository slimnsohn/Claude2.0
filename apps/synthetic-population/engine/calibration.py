"""Calibration gate: re-check anchor benchmarks after belief updates.

Real anchor values come from data/benchmarks.json (manually refreshed by the
user — never scraped). Verdicts: pass | drift_warning (dampening applied) |
stale (real numbers >STALE_DAYS old; no pass/fail claim, no dampening).
History appends to data/calibration_history.json (the legacy
data/calibration_results.json single-run dict is left untouched).
"""
import json
from datetime import datetime
from pathlib import Path

MAE_THRESHOLD = 0.05
STALE_DAYS = 30
DAMPENING_FACTOR = 0.5
CALIBRATION_RUNS = 5

ANCHOR_QUESTIONS = [
    "Do you approve of Trump's job performance?",
    "Is the economy getting better or worse?",
]


def get_anchor_real_values(data_dir, now: datetime = None) -> list:
    """Find anchor questions in benchmarks.json (fallback: curated list)."""
    now = now or datetime.now()
    path = Path(data_dir) / "benchmarks.json"
    saved = json.loads(path.read_text()) if path.exists() else []
    try:
        from api.benchmarks import CURATED_BENCHMARKS
    except Exception:
        CURATED_BENCHMARKS = []

    anchors = []
    for q in ANCHOR_QUESTIONS:
        entry = next((b for b in saved if b.get("question", "").lower() == q.lower()), None)
        if entry is None:
            entry = next((b for b in CURATED_BENCHMARKS
                          if b["question"].lower() == q.lower()), None)
        if entry is None or not entry.get("real_results"):
            continue
        stale = True
        try:
            d = datetime.strptime(entry.get("date", ""), "%Y-%m-%d")
            stale = (now - d).days > STALE_DAYS
        except ValueError:
            pass
        anchors.append({"question": q, "real": entry["real_results"],
                        "date": entry.get("date", ""), "stale": stale})
    return anchors


def synthetic_distribution(question: str, profiles: list, engine,
                           runs: int = CALIBRATION_RUNS) -> dict:
    """Archetype-weighted distribution, averaged over runs. No Flask required."""
    import pandas as pd
    from generator.archetypes import ArchetypeBuilder

    df = pd.DataFrame(profiles)
    builder = ArchetypeBuilder(min_cell_size=1)
    df = builder.build(df)
    weights = builder.get_weights()
    reps = {}
    for rec in df.to_dict(orient="records"):
        aid = rec.get("archetype_id")
        if aid and aid not in reps:
            reps[aid] = rec

    totals = {"yes": 0.0, "no": 0.0, "unsure": 0.0}
    for _ in range(runs):
        yes_w = no_w = unsure_w = total_w = 0.0
        for aid, w in weights.items():
            result = engine.get_opinion(question, reps.get(aid, {}))
            if result is None:
                continue
            opinion, _, _ = result
            if opinion == "yes":
                yes_w += w
            elif opinion == "no":
                no_w += w
            else:
                unsure_w += w
            total_w += w
        if total_w > 0:
            totals["yes"] += yes_w / total_w
            totals["no"] += no_w / total_w
            totals["unsure"] += unsure_w / total_w
    return {k: round(v / runs, 4) for k, v in totals.items()}


def dampen_beliefs(profiles: list, factor: float, now: datetime, run_id: str):
    for p in profiles:
        beliefs = p.get("beliefs") or {}
        touched = False
        for b in beliefs.values():
            if b.get("shift"):
                b["shift"] = round(b["shift"] * factor, 6)
                touched = True
        if touched:
            p.setdefault("drift_log", []).append({
                "date": now.isoformat(), "type": "calibration_dampening",
                "factor": factor, "update_id": run_id,
            })


def evaluate_anchors(anchors: list, poll_fn, profiles: list) -> list:
    results = []
    for a in anchors:
        synth = poll_fn(a["question"], profiles)
        mae = sum(abs(synth.get(k, 0) - a["real"].get(k, 0))
                  for k in ("yes", "no", "unsure")) / 3.0
        results.append({**a, "synthetic": synth, "mae": round(mae, 4)})
    return results


def run_calibration(data_dir, profiles: list, poll_fn, now: datetime = None,
                    run_id: str = "") -> dict:
    """poll_fn(question, profiles) -> {yes,no,unsure}. Returns verdict + anchor detail."""
    now = now or datetime.now()
    anchors = get_anchor_real_values(data_dir, now=now)

    result = {"run_id": run_id, "date": now.isoformat(), "anchors": [],
              "verdict": "stale", "dampened": False}
    if not anchors:
        result["verdict"] = "stale"
        result["note"] = "no anchor benchmarks found"
    elif any(a["stale"] for a in anchors):
        result["anchors"] = evaluate_anchors(anchors, poll_fn, profiles)
        result["verdict"] = "stale"
    else:
        result["anchors"] = evaluate_anchors(anchors, poll_fn, profiles)
        if all(a["mae"] > MAE_THRESHOLD for a in result["anchors"]):
            dampen_beliefs(profiles, DAMPENING_FACTOR, now, run_id)
            result["dampened"] = True
            result["anchors_after"] = evaluate_anchors(anchors, poll_fn, profiles)
            result["verdict"] = "drift_warning"
        else:
            result["verdict"] = "pass"

    hist_path = Path(data_dir) / "calibration_history.json"
    history = json.loads(hist_path.read_text()) if hist_path.exists() else []
    history.append(result)
    hist_path.write_text(json.dumps(history[-100:], indent=2))
    return result
