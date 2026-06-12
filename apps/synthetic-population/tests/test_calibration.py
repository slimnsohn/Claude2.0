# tests/test_calibration.py
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from engine.calibration import (
    MAE_THRESHOLD, STALE_DAYS, DAMPENING_FACTOR, ANCHOR_QUESTIONS,
    get_anchor_real_values, dampen_beliefs, evaluate_anchors, run_calibration,
)

NOW = datetime(2026, 6, 11, 9, 0, 0)


def _bench_file(tmp_path, date_str):
    d = tmp_path
    d.mkdir(parents=True, exist_ok=True)
    (d / "benchmarks.json").write_text(json.dumps([
        {"question": "Do you approve of Trump's job performance?",
         "real_results": {"yes": 0.46, "no": 0.50, "unsure": 0.04}, "date": date_str},
        {"question": "Is the economy getting better or worse?",
         "real_results": {"yes": 0.34, "no": 0.58, "unsure": 0.08}, "date": date_str},
    ]))
    return d


def test_anchor_loading_fresh(tmp_path):
    d = _bench_file(tmp_path, (NOW - timedelta(days=5)).strftime("%Y-%m-%d"))
    anchors = get_anchor_real_values(d, now=NOW)
    assert len(anchors) == 2
    assert not anchors[0]["stale"]


def test_anchor_stale_detection(tmp_path):
    d = _bench_file(tmp_path, (NOW - timedelta(days=45)).strftime("%Y-%m-%d"))
    anchors = get_anchor_real_values(d, now=NOW)
    assert all(a["stale"] for a in anchors)


def test_dampen_beliefs_halves_and_logs():
    profiles = [{"profile_id": "p1", "drift_log": [],
                 "beliefs": {"economy": {"shift": 0.10, "exposures": 4,
                                         "last_updated": NOW.isoformat()}}}]
    dampen_beliefs(profiles, DAMPENING_FACTOR, NOW, run_id="CY-X")
    assert profiles[0]["beliefs"]["economy"]["shift"] == pytest.approx(0.05)
    entry = profiles[0]["drift_log"][-1]
    assert entry["type"] == "calibration_dampening"
    assert entry["factor"] == DAMPENING_FACTOR


def test_run_calibration_verdicts(tmp_path):
    d = _bench_file(tmp_path, (NOW - timedelta(days=5)).strftime("%Y-%m-%d"))
    profiles = [{"profile_id": "p1", "drift_log": [], "beliefs": {}}]

    def good_poll(question, profs):
        if "approve" in question.lower():
            return {"yes": 0.46, "no": 0.50, "unsure": 0.04}
        return {"yes": 0.34, "no": 0.58, "unsure": 0.08}

    def bad_poll(question, profs):
        return {"yes": 0.70, "no": 0.27, "unsure": 0.03}

    def half_bad_poll(question, profs):
        if "approve" in question.lower():
            return {"yes": 0.46, "no": 0.50, "unsure": 0.04}
        return {"yes": 0.70, "no": 0.27, "unsure": 0.03}

    res = run_calibration(d, profiles, poll_fn=good_poll, now=NOW, run_id="CY-1")
    assert res["verdict"] == "pass"

    res = run_calibration(d, profiles, poll_fn=bad_poll, now=NOW, run_id="CY-2")
    assert res["verdict"] == "drift_warning"
    assert res["dampened"] is True

    # any-semantics: one bad anchor is enough to trigger drift_warning
    res = run_calibration(d, profiles, poll_fn=half_bad_poll, now=NOW, run_id="CY-2b")
    assert res["verdict"] == "drift_warning"

    d2 = tmp_path / "stale"
    d2.mkdir()
    _bench_file(d2, (NOW - timedelta(days=60)).strftime("%Y-%m-%d"))
    res = run_calibration(d2, profiles, poll_fn=bad_poll, now=NOW, run_id="CY-3")
    assert res["verdict"] == "stale"
    assert res["dampened"] is False


def test_history_appended(tmp_path):
    d = _bench_file(tmp_path, (NOW - timedelta(days=5)).strftime("%Y-%m-%d"))
    profiles = [{"profile_id": "p1", "drift_log": [], "beliefs": {}}]
    def good_poll(question, profs):
        if "approve" in question.lower():
            return {"yes": 0.46, "no": 0.50, "unsure": 0.04}
        return {"yes": 0.34, "no": 0.58, "unsure": 0.08}

    run_calibration(d, profiles, poll_fn=good_poll, now=NOW, run_id="CY-1")
    hist = json.loads((d / "calibration_history.json").read_text())
    assert isinstance(hist, list) and hist[-1]["run_id"] == "CY-1"
