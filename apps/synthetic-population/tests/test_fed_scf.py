"""Tests for the Fed SCF (Survey of Consumer Finances) source plugin."""

import pytest
import pandas as pd

from pipeline.sources.fed_scf import (
    FedSCFSource,
    RISK_TOLERANCE_MAP,
    INVESTMENT_TYPES_MAP,
    DEBT_LEVEL_MAP,
    NET_WORTH_BRACKET_MAP,
    FINANCIAL_PLANNING_HORIZON_MAP,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def source():
    return FedSCFSource()


@pytest.fixture
def raw_scf_data():
    """Minimal SCF-shaped DataFrame covering key columns."""
    return pd.DataFrame({
        "RISKTOL": [1, 3, 4],             # substantial risk, average, no risk
        "HFINX": [1, 5, 8],              # stocks, retirement_accounts, none
        "DEBT_QUINTILE": [1, 3, 5],      # none_to_low, moderate, very_high
        "SAVEMONTHS": [12, 3, 0],        # months of savings (numeric)
        "NW_BRACKET": [5, 3, 1],         # high, middle, negative_to_zero
        "PLANNING": [5, 3, 1],           # longer than 10 years, few years, few months
        "age_bracket": ["35-44", "55-64", "25-34"],
        "sex": ["M", "F", "M"],
        "race": ["white", "black", "hispanic"],
        "education": ["graduate", "bachelors", "hs_diploma"],
        "income_bracket": ["150k+", "75-100k", "25-50k"],
    })


# ---------------------------------------------------------------------------
# Metadata tests
# ---------------------------------------------------------------------------

def test_source_name(source):
    assert source.name == "fed_scf"


def test_update_cycle(source):
    assert source.update_cycle == "triennial"


def test_variables_provided(source):
    expected = ["risk_tolerance", "investment_types", "debt_level", "savings_months"]
    for var in expected:
        assert var in source.variables_provided, f"Missing variable: {var}"


def test_variables_provided_count(source):
    assert len(source.variables_provided) == 4


# ---------------------------------------------------------------------------
# Match keys
# ---------------------------------------------------------------------------

def test_match_keys(source):
    for key in ["age_bracket", "sex", "race", "education", "income_bracket"]:
        assert key in source.match_keys


def test_match_keys_count(source):
    assert len(source.match_keys) == 5


# ---------------------------------------------------------------------------
# Variable mapping tests — standard columns
# ---------------------------------------------------------------------------

def test_risk_tolerance_mapping(source, raw_scf_data):
    cleaned = source.clean(raw_scf_data)
    result = source.harmonize(cleaned)
    # RISKTOL: [1, 3, 4] → [1.0, 0.33, 0.0]
    assert list(result["risk_tolerance"]) == [1.0, 0.33, 0.0]


def test_investment_types_mapping(source, raw_scf_data):
    cleaned = source.clean(raw_scf_data)
    result = source.harmonize(cleaned)
    assert list(result["investment_types"]) == ["stocks", "retirement_accounts", "none"]


def test_debt_level_mapping(source, raw_scf_data):
    cleaned = source.clean(raw_scf_data)
    result = source.harmonize(cleaned)
    assert list(result["debt_level"]) == ["none_to_low", "moderate", "very_high"]


def test_savings_months_passthrough(source, raw_scf_data):
    cleaned = source.clean(raw_scf_data)
    result = source.harmonize(cleaned)
    # savings_months has no map — passed through as numeric
    assert list(result["savings_months"]) == [12, 3, 0]


# ---------------------------------------------------------------------------
# Custom column tests — namespaced as fed_scf:{name}
# ---------------------------------------------------------------------------

def test_net_worth_bracket_custom_column(source, raw_scf_data):
    cleaned = source.clean(raw_scf_data)
    result = source.harmonize(cleaned)
    assert "fed_scf:net_worth_bracket" in result.columns
    assert list(result["fed_scf:net_worth_bracket"]) == ["high", "middle", "negative_to_zero"]


def test_financial_planning_horizon_custom_column(source, raw_scf_data):
    cleaned = source.clean(raw_scf_data)
    result = source.harmonize(cleaned)
    assert "fed_scf:financial_planning_horizon" in result.columns
    assert list(result["fed_scf:financial_planning_horizon"]) == [
        "longer_than_10_years", "next_few_years", "next_few_months"
    ]


def test_custom_columns_definition(source):
    assert "net_worth_bracket" in source.custom_columns
    assert "financial_planning_horizon" in source.custom_columns


# ---------------------------------------------------------------------------
# clean() behavior
# ---------------------------------------------------------------------------

def test_clean_accepts_dataframe(source, raw_scf_data):
    result = source.clean(raw_scf_data)
    assert isinstance(result, pd.DataFrame)
    assert "RISKTOL" in result.columns


def test_clean_does_not_mutate_input(source, raw_scf_data):
    original_cols = list(raw_scf_data.columns)
    source.clean(raw_scf_data)
    assert list(raw_scf_data.columns) == original_cols


# ---------------------------------------------------------------------------
# harmonize() behavior
# ---------------------------------------------------------------------------

def test_harmonize_renames_raw_columns(source, raw_scf_data):
    cleaned = source.clean(raw_scf_data)
    result = source.harmonize(cleaned)
    assert "risk_tolerance" in result.columns
    assert "RISKTOL" not in result.columns


def test_match_keys_preserved_after_harmonize(source, raw_scf_data):
    cleaned = source.clean(raw_scf_data)
    result = source.harmonize(cleaned)
    assert list(result["income_bracket"]) == ["150k+", "75-100k", "25-50k"]
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
    assert cfg["source"] == "fed_scf"
    assert cfg["match_keys"] == source.match_keys
    assert cfg["variables"] == source.variables_provided
