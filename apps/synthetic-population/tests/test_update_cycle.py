# tests/test_update_cycle.py
import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

from engine.update_cycle import run_cycle

NOW = datetime(2026, 6, 11, 9, 0, 0)

HEADLINES = [
    {"title": "Inflation falls to 2.1 percent as economy beats expectations",
     "description": "Markets rally on strong jobs growth", "feed": "AP"},
    {"title": "Border crossings hit record high amid policy fight",
     "description": "", "feed": "BBC"},
]


def _setup_data(tmp_path):
    d = tmp_path / "data"
    (d / "profiles").mkdir(parents=True)
    profiles = [{
        "profile_id": f"p{i:07d}", "party_id": "rep" if i % 2 else "dem",
        "primary_news_source": "fox_news" if i % 2 else "msnbc",
        "education": "bachelors", "age_bracket": "35-44", "race": "white",
        "urban_rural": "suburban", "religion_attendance": "rarely",
        "beliefs": {}, "drift_log": [],
    } for i in range(10)]
    (d / "profiles" / "registry.json").write_text(json.dumps(profiles))
    (d / "benchmarks.json").write_text(json.dumps([
        {"question": "Do you approve of Trump's job performance?",
         "real_results": {"yes": 0.46, "no": 0.50, "unsure": 0.04},
         "date": (NOW - timedelta(days=3)).strftime("%Y-%m-%d")},
        {"question": "Is the economy getting better or worse?",
         "real_results": {"yes": 0.34, "no": 0.58, "unsure": 0.08},
         "date": (NOW - timedelta(days=3)).strftime("%Y-%m-%d")},
    ]))
    return d


def _fake_engine():
    eng = MagicMock()
    eng.get_opinion.return_value = ("yes", 6, "test")
    return eng


def test_run_cycle_full_pipeline(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    d = _setup_data(tmp_path)
    summary = run_cycle(d, _fake_engine(), fetch_fn=lambda: HEADLINES, now=NOW)

    assert summary["n_events"] == 2
    assert summary["scoring_method"] == "keyword"
    assert "calibration" in summary

    profiles = json.loads((d / "profiles" / "registry.json").read_text())
    assert any(p["beliefs"] for p in profiles)           # someone was exposed
    history = json.loads((d / "belief_history.json").read_text())
    assert history[-1]["update_id"] == summary["update_id"]
    updates = json.loads((d / "world_updates.json").read_text())
    assert all(u["source"] == "auto" for u in updates)
    assert all("shifts" in u for u in updates)            # legacy compat field


def test_run_cycle_no_headlines_still_decays(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    d = _setup_data(tmp_path)
    profiles = json.loads((d / "profiles" / "registry.json").read_text())
    profiles[0]["beliefs"] = {"economy": {"shift": 0.10, "exposures": 1,
                                          "last_updated": (NOW - timedelta(days=14)).isoformat()}}
    (d / "profiles" / "registry.json").write_text(json.dumps(profiles))

    summary = run_cycle(d, None, fetch_fn=lambda: [], now=NOW)
    assert summary["n_events"] == 0
    out = json.loads((d / "profiles" / "registry.json").read_text())
    assert abs(out[0]["beliefs"]["economy"]["shift"] - 0.05) < 1e-6
