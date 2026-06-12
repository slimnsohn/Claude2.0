# tests/test_beliefs.py
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from engine.beliefs import (
    OUTLET_FAMILY, BELIEF_BOUND, HALF_LIFE_DAYS, CES_TOPIC_TO_BELIEF, BELIEF_SIGN,
    decay_factor, decay_beliefs, exposure_prob, susceptibility, apply_event,
    update_population,
)
from engine.registry_io import load_registry, save_registry

NOW = datetime(2026, 6, 11, 9, 0, 0)

EVENT = {
    "text": "Economy surges", "topics": ["economy"], "direction": 0.8,
    "salience": 1.0, "framing": {"right": 1.0, "left": 1.0, "mainstream": 1.0},
}


def _profile(**over):
    p = {"profile_id": "abc12345", "party_id": "independent",
         "primary_news_source": "local_tv", "beliefs": {}, "drift_log": []}
    p.update(over)
    return p


def test_decay_factor_half_life():
    assert decay_factor(0) == pytest.approx(1.0)
    assert decay_factor(HALF_LIFE_DAYS) == pytest.approx(0.5)
    assert decay_factor(2 * HALF_LIFE_DAYS) == pytest.approx(0.25)


def test_decay_beliefs_moves_toward_zero():
    p = _profile(beliefs={"economy": {"shift": 0.10, "exposures": 3,
                                      "last_updated": (NOW - timedelta(days=14)).isoformat()}})
    decay_beliefs(p, NOW)
    assert p["beliefs"]["economy"]["shift"] == pytest.approx(0.05)


def test_exposure_prob_bounds():
    assert exposure_prob(1.0, 1.0) == 1.0
    assert exposure_prob(0.4, 0.0) == pytest.approx(0.2)
    assert 0.0 <= exposure_prob(0.1, 0.3) <= 1.0


def test_susceptibility_confirmation_bias():
    # Positive economy news favors incumbent (rep): congenial for reps, counter for dems
    assert susceptibility("strong_dem", "economy", +1.0) == pytest.approx(0.7 * 0.4)
    assert susceptibility("strong_rep", "economy", +1.0) == pytest.approx(0.7)
    assert susceptibility("lean_dem", "economy", +1.0) == pytest.approx(0.4)
    assert susceptibility("independent", "economy", +1.0) == pytest.approx(1.0)


def test_apply_event_bounded_and_logged():
    import random
    p = _profile(party_id="rep", primary_news_source="fox_news",
                 beliefs={"economy": {"shift": 0.149, "exposures": 50,
                                      "last_updated": NOW.isoformat()}})
    rng = random.Random(0)  # exposure_prob = 1.0 for this event, always seen
    delta = apply_event(p, EVENT, NOW, rng, update_id="CY-TEST")
    assert p["beliefs"]["economy"]["shift"] <= BELIEF_BOUND
    assert p["drift_log"][-1]["update_id"] == "CY-TEST"
    assert p["drift_log"][-1]["topic"] == "economy"


def test_update_population_deterministic_and_summary():
    profiles = [_profile(profile_id=f"p{i:07d}", party_id="rep",
                         primary_news_source="fox_news") for i in range(20)]
    import copy
    profiles2 = copy.deepcopy(profiles)
    s1 = update_population(profiles, [EVENT], NOW, update_id="CY-1")
    s2 = update_population(profiles2, [EVENT], NOW, update_id="CY-1")
    assert profiles == profiles2          # same update_id → same exposures
    assert s1["exposures"] == s2["exposures"]
    assert "economy" in s1["mean_shift_by_topic"]
    assert s1["mean_shift_by_topic"]["economy"] > 0


def test_registry_io_atomic_backup(tmp_path):
    d = tmp_path / "data"
    (d / "profiles").mkdir(parents=True)
    (d / "profiles" / "registry.json").write_text(json.dumps([{"profile_id": "old"}]))
    save_registry(d, [{"profile_id": "new"}])
    assert load_registry(d)[0]["profile_id"] == "new"
    backups = list((d / "profiles").glob("registry.backup.*.json"))
    assert len(backups) == 1
    assert json.loads(backups[0].read_text())[0]["profile_id"] == "old"


def test_topic_and_sign_maps_cover_ces_columns():
    from engine.ces_columns import CES_COLUMNS
    for col_id, col in CES_COLUMNS.items():
        assert col["topic"] in CES_TOPIC_TO_BELIEF, col_id
        assert col_id in BELIEF_SIGN, col_id
