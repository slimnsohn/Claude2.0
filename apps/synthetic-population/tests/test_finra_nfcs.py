"""Tests for the FINRA NFCS (National Financial Capability Study) source plugin."""

import pytest
import pandas as pd

from pipeline.sources.finra_nfcs import (
    FINRANFCSSource,
    FINANCIAL_LITERACY_SCORE_MAP,
    FINANCIAL_SOPHISTICATION_MAP,
    TAX_APPROACH_MAP,
    RETIREMENT_STRATEGY_MAP,
    INSURANCE_COVERAGE_MAP,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def source():
    return FINRANFCSSource()


@pytest.fixture
def raw_nfcs_data():
    """Minimal NFCS-shaped DataFrame covering key columns."""
    return pd.DataFrame({
        "M4": [5, 3, 0],              # financial literacy: high, mid, none
        "M6": [7, 4, 1],              # sophistication: max, mid, min
        "J5": [1, 4, 2],              # tax: itemize, software, standard
        "C4A": [1, 5, 2],             # retirement: 401k, no_plan, pension
        "L1": [1, 2, 1],              # uses_advisor: yes, no, yes
        "H1": [4, 2, 0],              # insurance: comprehensive, partial, none
        "age_bracket": ["35-44", "25-34", "55-64"],
        "sex": ["M", "F", "M"],
        "race": ["white", "hispanic", "black"],
        "education": ["graduate", "some_college", "bachelors"],
        "income_bracket": ["100-150k", "25-50k", "75-100k"],
    })


# ---------------------------------------------------------------------------
# Metadata tests
# ---------------------------------------------------------------------------

def test_source_name(source):
    assert source.name == "finra_nfcs"


def test_update_cycle(source):
    assert source.update_cycle == "triennial"


def test_variables_provided(source):
    expected = [
        "financial_literacy_score", "financial_sophistication",
        "tax_approach", "retirement_strategy",
        "uses_financial_advisor", "insurance_coverage",
    ]
    for var in expected:
        assert var in source.variables_provided, f"Missing variable: {var}"


def test_variables_provided_count(source):
    assert len(source.variables_provided) == 6


# ---------------------------------------------------------------------------
# Match keys
# ---------------------------------------------------------------------------

def test_match_keys(source):
    for key in ["age_bracket", "sex", "race", "education", "income_bracket"]:
        assert key in source.match_keys


def test_match_keys_count(source):
    assert len(source.match_keys) == 5


# ---------------------------------------------------------------------------
# Variable mapping tests
# ---------------------------------------------------------------------------

def test_financial_literacy_score_mapping(source, raw_nfcs_data):
    cleaned = source.clean(raw_nfcs_data)
    result = source.harmonize(cleaned)
    # M4: [5, 3, 0] → [1.0, 0.6, 0.0]
    assert list(result["financial_literacy_score"]) == [1.0, 0.6, 0.0]


def test_financial_sophistication_mapping(source, raw_nfcs_data):
    cleaned = source.clean(raw_nfcs_data)
    result = source.harmonize(cleaned)
    # M6: [7, 4, 1] → [1.0, 0.5, 0.0]
    assert list(result["financial_sophistication"]) == [1.0, 0.5, 0.0]


def test_tax_approach_mapping(source, raw_nfcs_data):
    cleaned = source.clean(raw_nfcs_data)
    result = source.harmonize(cleaned)
    assert list(result["tax_approach"]) == ["itemize", "software", "standard_deduction"]


def test_retirement_strategy_mapping(source, raw_nfcs_data):
    cleaned = source.clean(raw_nfcs_data)
    result = source.harmonize(cleaned)
    assert list(result["retirement_strategy"]) == ["401k_ira", "no_plan", "pension"]


def test_uses_financial_advisor_mapping(source, raw_nfcs_data):
    cleaned = source.clean(raw_nfcs_data)
    result = source.harmonize(cleaned)
    assert list(result["uses_financial_advisor"]) == [True, False, True]


def test_insurance_coverage_mapping(source, raw_nfcs_data):
    cleaned = source.clean(raw_nfcs_data)
    result = source.harmonize(cleaned)
    assert list(result["insurance_coverage"]) == ["comprehensive", "partial", "none"]


# ---------------------------------------------------------------------------
# clean() behavior
# ---------------------------------------------------------------------------

def test_clean_accepts_dataframe(source, raw_nfcs_data):
    result = source.clean(raw_nfcs_data)
    assert isinstance(result, pd.DataFrame)
    assert "M4" in result.columns


def test_clean_does_not_mutate_input(source, raw_nfcs_data):
    original_cols = list(raw_nfcs_data.columns)
    source.clean(raw_nfcs_data)
    assert list(raw_nfcs_data.columns) == original_cols


# ---------------------------------------------------------------------------
# harmonize() behavior
# ---------------------------------------------------------------------------

def test_harmonize_renames_raw_columns(source, raw_nfcs_data):
    cleaned = source.clean(raw_nfcs_data)
    result = source.harmonize(cleaned)
    assert "financial_literacy_score" in result.columns
    assert "M4" not in result.columns


def test_match_keys_preserved_after_harmonize(source, raw_nfcs_data):
    cleaned = source.clean(raw_nfcs_data)
    result = source.harmonize(cleaned)
    assert list(result["income_bracket"]) == ["100-150k", "25-50k", "75-100k"]
    assert list(result["education"]) == ["graduate", "some_college", "bachelors"]


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
    assert cfg["source"] == "finra_nfcs"
    assert cfg["match_keys"] == source.match_keys
    assert cfg["variables"] == source.variables_provided
