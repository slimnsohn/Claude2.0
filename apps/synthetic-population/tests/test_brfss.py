"""Tests for the BRFSS (CDC Behavioral Risk Factor Surveillance System) source plugin."""

import pytest
import pandas as pd

from pipeline.sources.brfss import (
    BRFSSSource,
    HEALTH_INSURANCE_MAP,
    DISABILITY_MAP,
    EXERCISE_FREQUENCY_MAP,
    TOBACCO_USE_MAP,
    ALCOHOL_USE_MAP,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def source():
    return BRFSSSource()


@pytest.fixture
def raw_brfss_data():
    """Minimal BRFSS-shaped DataFrame covering key columns."""
    return pd.DataFrame({
        "HLTHPLN1": [1, 2, 1],        # health insurance: yes, no, yes
        "DIFFWALK": [2, 1, 2],        # disability: no, yes, no
        "CHCCOPD2": [2, 1, 2],        # chronic conditions: no, yes, no
        "EXERANY2": [1, 2, 1],        # exercise: active, sedentary, active
        "SMOKDAY2": [3, 1, 2],        # tobacco: not_at_all, daily, some_days
        "DRNKANY5": [1, 2, 1],        # alcohol: yes, no, yes
        "MENTHLTH": [0, 15, 3],       # mental health days bad
        "age_bracket": ["25-34", "55-64", "45-54"],
        "sex": ["F", "M", "F"],
        "race": ["white", "black", "hispanic"],
        "education": ["bachelors", "hs_diploma", "some_college"],
        "state": ["CA", "TX", "NY"],
    })


# ---------------------------------------------------------------------------
# Metadata tests
# ---------------------------------------------------------------------------

def test_source_name(source):
    assert source.name == "brfss"


def test_update_cycle(source):
    assert source.update_cycle == "annual"


def test_variables_provided(source):
    for var in ["health_insurance", "disability"]:
        assert var in source.variables_provided, f"Missing variable: {var}"


def test_variables_provided_count(source):
    assert len(source.variables_provided) == 2


# ---------------------------------------------------------------------------
# Match keys
# ---------------------------------------------------------------------------

def test_match_keys(source):
    for key in ["age_bracket", "sex", "race", "education", "state"]:
        assert key in source.match_keys


def test_match_keys_count(source):
    assert len(source.match_keys) == 5


# ---------------------------------------------------------------------------
# Variable mapping tests — standard columns
# ---------------------------------------------------------------------------

def test_health_insurance_mapping(source, raw_brfss_data):
    cleaned = source.clean(raw_brfss_data)
    result = source.harmonize(cleaned)
    assert list(result["health_insurance"]) == [True, False, True]


def test_disability_mapping(source, raw_brfss_data):
    cleaned = source.clean(raw_brfss_data)
    result = source.harmonize(cleaned)
    assert list(result["disability"]) == [False, True, False]


# ---------------------------------------------------------------------------
# Custom column tests — namespaced as brfss:{name}
# ---------------------------------------------------------------------------

def test_exercise_frequency_custom_column(source, raw_brfss_data):
    cleaned = source.clean(raw_brfss_data)
    result = source.harmonize(cleaned)
    assert "brfss:exercise_frequency" in result.columns
    assert list(result["brfss:exercise_frequency"]) == ["active", "sedentary", "active"]


def test_tobacco_use_custom_column(source, raw_brfss_data):
    cleaned = source.clean(raw_brfss_data)
    result = source.harmonize(cleaned)
    assert "brfss:tobacco_use" in result.columns
    assert list(result["brfss:tobacco_use"]) == ["not_at_all", "daily", "some_days"]


def test_alcohol_use_custom_column(source, raw_brfss_data):
    cleaned = source.clean(raw_brfss_data)
    result = source.harmonize(cleaned)
    assert "brfss:alcohol_use" in result.columns
    assert list(result["brfss:alcohol_use"]) == [True, False, True]


def test_mental_health_days_passthrough(source, raw_brfss_data):
    cleaned = source.clean(raw_brfss_data)
    result = source.harmonize(cleaned)
    assert "brfss:mental_health_days" in result.columns
    assert list(result["brfss:mental_health_days"]) == [0, 15, 3]


def test_custom_columns_definition(source):
    assert "chronic_conditions" in source.custom_columns
    assert "exercise_frequency" in source.custom_columns
    assert "tobacco_use" in source.custom_columns
    assert "alcohol_use" in source.custom_columns
    assert "mental_health_days" in source.custom_columns


# ---------------------------------------------------------------------------
# clean() behavior
# ---------------------------------------------------------------------------

def test_clean_accepts_dataframe(source, raw_brfss_data):
    result = source.clean(raw_brfss_data)
    assert isinstance(result, pd.DataFrame)
    assert "HLTHPLN1" in result.columns


def test_clean_does_not_mutate_input(source, raw_brfss_data):
    original_cols = list(raw_brfss_data.columns)
    source.clean(raw_brfss_data)
    assert list(raw_brfss_data.columns) == original_cols


# ---------------------------------------------------------------------------
# harmonize() behavior
# ---------------------------------------------------------------------------

def test_match_keys_preserved_after_harmonize(source, raw_brfss_data):
    cleaned = source.clean(raw_brfss_data)
    result = source.harmonize(cleaned)
    assert list(result["state"]) == ["CA", "TX", "NY"]
    assert list(result["sex"]) == ["F", "M", "F"]


# ---------------------------------------------------------------------------
# download() raises NotImplementedError
# ---------------------------------------------------------------------------

def test_download_raises(source):
    with pytest.raises(NotImplementedError):
        source.download()


# ---------------------------------------------------------------------------
# match_config()
# ---------------------------------------------------------------------------

def test_match_config_structure(source):
    cfg = source.match_config()
    assert cfg["source"] == "brfss"
    assert cfg["match_keys"] == source.match_keys
    assert cfg["variables"] == source.variables_provided
