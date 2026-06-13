"""Tests for the CPS (Current Population Survey) source plugin."""

import pytest
import pandas as pd

from pipeline.sources.cps import (
    CPSSource,
    EMPLOYMENT_STATUS_MAP,
    OCCUPATION_MAP,
    INDUSTRY_MAP,
    UNION_MEMBERSHIP_MAP,
    INCOME_SOURCE_MAP,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def source():
    return CPSSource()


@pytest.fixture
def raw_cps_data():
    """Minimal CPS-shaped DataFrame covering key columns."""
    return pd.DataFrame({
        "PEMLR": [1, 3, 5],           # employed at work, unemployed layoff, not in LF
        "PRDTOCC1": [1, 3, 7],        # management, service, production
        "PRDTIND1": [4, 6, 11],       # manufacturing, retail, education/health
        "PEABSRSN": [1, 2, 3],        # union member, covered not member, not covered
        "PEHRUSL1": [40, 25, 0],      # hours worked (numeric)
        "HEFAMINC": [1, 8, 9],        # wages, retirement, other
        "age_bracket": ["25-34", "45-54", "65+"],
        "sex": ["M", "F", "M"],
        "race": ["white", "black", "hispanic"],
        "education": ["bachelors", "hs_diploma", "graduate"],
        "state": ["TX", "CA", "FL"],
    })


# ---------------------------------------------------------------------------
# Metadata tests
# ---------------------------------------------------------------------------

def test_source_name(source):
    assert source.name == "cps"


def test_update_cycle(source):
    assert source.update_cycle == "monthly"


def test_variables_provided(source):
    expected = [
        "employment_status", "occupation", "industry",
        "union_membership", "hours_worked", "income_source",
    ]
    for var in expected:
        assert var in source.variables_provided, f"Missing variable: {var}"


def test_variables_provided_count(source):
    assert len(source.variables_provided) == 6


# ---------------------------------------------------------------------------
# Match keys
# ---------------------------------------------------------------------------

def test_match_keys(source):
    for key in ["age_bracket", "sex", "race", "education", "state"]:
        assert key in source.match_keys


def test_match_keys_count(source):
    assert len(source.match_keys) == 5


# ---------------------------------------------------------------------------
# Variable mapping tests
# ---------------------------------------------------------------------------

def test_employment_status_mapping(source, raw_cps_data):
    cleaned = source.clean(raw_cps_data)
    result = source.harmonize(cleaned)
    assert list(result["employment_status"]) == [
        "employed_at_work", "unemployed_layoff", "not_in_labor_force"
    ]


def test_occupation_mapping(source, raw_cps_data):
    cleaned = source.clean(raw_cps_data)
    result = source.harmonize(cleaned)
    assert list(result["occupation"]) == ["management", "service", "production"]


def test_industry_mapping(source, raw_cps_data):
    cleaned = source.clean(raw_cps_data)
    result = source.harmonize(cleaned)
    assert list(result["industry"]) == ["manufacturing", "retail_trade", "education_health"]


def test_hours_worked_passthrough(source, raw_cps_data):
    cleaned = source.clean(raw_cps_data)
    result = source.harmonize(cleaned)
    # hours_worked has no map — should pass through as-is
    assert list(result["hours_worked"]) == [40, 25, 0]


def test_income_source_mapping(source, raw_cps_data):
    cleaned = source.clean(raw_cps_data)
    result = source.harmonize(cleaned)
    assert list(result["income_source"]) == ["wages_salaries", "retirement", "other"]


# ---------------------------------------------------------------------------
# clean() behavior
# ---------------------------------------------------------------------------

def test_clean_accepts_dataframe(source, raw_cps_data):
    result = source.clean(raw_cps_data)
    assert isinstance(result, pd.DataFrame)
    assert "PEMLR" in result.columns


def test_clean_does_not_mutate_input(source, raw_cps_data):
    original_cols = list(raw_cps_data.columns)
    source.clean(raw_cps_data)
    assert list(raw_cps_data.columns) == original_cols


def test_clean_drops_all_na_rows(source):
    df = pd.DataFrame({
        "PEMLR": [1.0, None],
        "PRDTOCC1": [None, None],
        "PRDTIND1": [None, None],
        "PEHRUSL1": [None, None],
    })
    cleaned = source.clean(df)
    assert len(cleaned) == 1


# ---------------------------------------------------------------------------
# harmonize() behavior
# ---------------------------------------------------------------------------

def test_harmonize_renames_raw_columns(source, raw_cps_data):
    cleaned = source.clean(raw_cps_data)
    result = source.harmonize(cleaned)
    assert "employment_status" in result.columns
    assert "PEMLR" not in result.columns


def test_match_keys_preserved_after_harmonize(source, raw_cps_data):
    cleaned = source.clean(raw_cps_data)
    result = source.harmonize(cleaned)
    assert list(result["state"]) == ["TX", "CA", "FL"]
    assert list(result["sex"]) == ["M", "F", "M"]


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
    assert cfg["source"] == "cps"
    assert cfg["match_keys"] == source.match_keys
    assert cfg["variables"] == source.variables_provided
