import pytest
from monitor.drift import DriftEngine


def test_drift_adjusts_responsive_variable():
    profile = {
        "party_id": "lean_rep",
        "climate_policy_support": 0.3,
        "drift_log": [],
    }
    event = {
        "event_id": "EVT-001",
        "affected_segments": {
            "party_id": {"lean_rep": {"climate_policy_support": +0.1}},
        },
    }
    updated = DriftEngine.apply(profile, event)
    assert updated["climate_policy_support"] == pytest.approx(0.4)
    assert len(updated["drift_log"]) == 1


def test_drift_clamps_to_bounds():
    profile = {
        "party_id": "strong_dem",
        "climate_policy_support": 0.95,
        "drift_log": [],
    }
    event = {
        "event_id": "EVT-002",
        "affected_segments": {
            "party_id": {"strong_dem": {"climate_policy_support": +0.2}},
        },
    }
    updated = DriftEngine.apply(profile, event)
    assert updated["climate_policy_support"] <= 1.0


def test_drift_ignores_immutable_variables():
    profile = {
        "party_id": "lean_rep",
        "race": "white",
        "drift_log": [],
    }
    event = {
        "event_id": "EVT-003",
        "affected_segments": {
            "party_id": {"lean_rep": {"race": "hispanic"}},
        },
    }
    updated = DriftEngine.apply(profile, event)
    assert updated["race"] == "white"


def test_drift_ignores_unaffected_profiles():
    profile = {
        "party_id": "strong_dem",
        "climate_policy_support": 0.9,
        "drift_log": [],
    }
    event = {
        "event_id": "EVT-004",
        "affected_segments": {
            "party_id": {"lean_rep": {"climate_policy_support": +0.1}},
        },
    }
    updated = DriftEngine.apply(profile, event)
    assert updated["climate_policy_support"] == 0.9
    assert len(updated["drift_log"]) == 0


# --- Additional edge case tests ---

def test_drift_does_not_mutate_original_profile():
    profile = {
        "party_id": "lean_rep",
        "climate_policy_support": 0.3,
        "drift_log": [],
    }
    event = {
        "event_id": "EVT-005",
        "affected_segments": {
            "party_id": {"lean_rep": {"climate_policy_support": +0.1}},
        },
    }
    DriftEngine.apply(profile, event)
    assert profile["climate_policy_support"] == 0.3
    assert len(profile["drift_log"]) == 0


def test_drift_clamps_lower_bound():
    profile = {
        "party_id": "lean_rep",
        "climate_policy_support": 0.05,
        "drift_log": [],
    }
    event = {
        "event_id": "EVT-006",
        "affected_segments": {
            "party_id": {"lean_rep": {"climate_policy_support": -0.2}},
        },
    }
    updated = DriftEngine.apply(profile, event)
    assert updated["climate_policy_support"] >= 0.0


def test_drift_ignores_slow_vars():
    profile = {
        "party_id": "lean_rep",
        "religion_affiliation": "catholic",
        "drift_log": [],
    }
    event = {
        "event_id": "EVT-007",
        "affected_segments": {
            "party_id": {"lean_rep": {"religion_affiliation": "protestant"}},
        },
    }
    updated = DriftEngine.apply(profile, event)
    assert updated["religion_affiliation"] == "catholic"
    assert len(updated["drift_log"]) == 0


def test_drift_log_entry_shape():
    profile = {
        "party_id": "lean_rep",
        "climate_policy_support": 0.3,
        "drift_log": [],
    }
    event = {
        "event_id": "EVT-008",
        "affected_segments": {
            "party_id": {"lean_rep": {"climate_policy_support": +0.1}},
        },
    }
    updated = DriftEngine.apply(profile, event)
    entry = updated["drift_log"][0]
    assert entry["event_id"] == "EVT-008"
    assert entry["variable"] == "climate_policy_support"
    assert entry["old_value"] == pytest.approx(0.3)
    assert entry["new_value"] == pytest.approx(0.4)


def test_apply_batch():
    profiles = [
        {"party_id": "lean_rep", "climate_policy_support": 0.3, "drift_log": []},
        {"party_id": "strong_dem", "climate_policy_support": 0.8, "drift_log": []},
        {"party_id": "lean_rep", "climate_policy_support": 0.5, "drift_log": []},
    ]
    event = {
        "event_id": "EVT-BATCH",
        "affected_segments": {
            "party_id": {"lean_rep": {"climate_policy_support": +0.1}},
        },
    }
    results = DriftEngine.apply_batch(profiles, event)
    assert results[0]["climate_policy_support"] == pytest.approx(0.4)
    assert results[1]["climate_policy_support"] == pytest.approx(0.8)  # unaffected
    assert results[2]["climate_policy_support"] == pytest.approx(0.6)
    # Originals not mutated
    assert profiles[0]["climate_policy_support"] == 0.3
