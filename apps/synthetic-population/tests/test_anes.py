"""Tests for the ANES (American National Election Studies) source plugin."""

import pytest
import pandas as pd

from pipeline.sources.anes import (
    ANESSource,
    _SCALE_5PT_MAP,
    _RESENTMENT_MAP,
    _AUTH_MAP,
    _SOCIAL_TRUST_MAP,
    _CONFIDENCE_MAP,
    _MERITOCRACY_MAP,
    _EFFICACY_MAP,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def source():
    return ANESSource()


@pytest.fixture
def raw_anes_data():
    """Minimal ANES-shaped DataFrame covering key columns."""
    return pd.DataFrame({
        "V201600": [1, 3, 5],        # racial_resentment: high, mid, low
        "V201626": [4, 2, 0],        # authoritarianism: high, mid, none
        "V201233": [1, 2, 3],        # social_trust: trust, no trust, depends
        "V162333": [5, 3, 1],        # openness: high, mid, low
        "V162334": [4, 3, 2],        # conscientiousness
        "V162335": [1, 3, 5],        # extraversion
        "V162336": [5, 4, 3],        # agreeableness
        "V162337": [2, 3, 4],        # neuroticism
        "V201228": [1, 2, 3],        # institutional_confidence
        "V201401": [1, 3, 5],        # meritocracy_belief
        "V201379": [1, 3, 5],        # political_efficacy
        "age_bracket": ["18-24", "35-44", "65+"],
        "sex": ["F", "M", "F"],
        "race": ["white", "black", "hispanic"],
        "education": ["hs_diploma", "bachelors", "graduate"],
        "party_id": ["strong_dem", "independent", "strong_rep"],
    })


# ---------------------------------------------------------------------------
# Metadata tests
# ---------------------------------------------------------------------------

def test_source_name(source):
    assert source.name == "anes"


def test_update_cycle(source):
    assert source.update_cycle == "election_year"


def test_variables_provided(source):
    expected = [
        "racial_resentment", "authoritarianism", "social_trust",
        "openness", "conscientiousness", "extraversion",
        "agreeableness", "neuroticism", "institutional_confidence",
        "meritocracy_belief", "political_efficacy",
    ]
    for var in expected:
        assert var in source.variables_provided, f"Missing variable: {var}"


def test_variables_provided_count(source):
    assert len(source.variables_provided) == 11


# ---------------------------------------------------------------------------
# Match keys
# ---------------------------------------------------------------------------

def test_match_keys(source):
    for key in ["age_bracket", "sex", "race", "education", "party_id"]:
        assert key in source.match_keys


def test_match_keys_count(source):
    assert len(source.match_keys) == 5


# ---------------------------------------------------------------------------
# Variable mapping tests
# ---------------------------------------------------------------------------

def test_racial_resentment_mapping(source, raw_anes_data):
    cleaned = source.clean(raw_anes_data)
    result = source.harmonize(cleaned)
    # V201600: [1, 3, 5] → [1.0, 0.5, 0.0]
    assert list(result["racial_resentment"]) == [1.0, 0.5, 0.0]


def test_social_trust_mapping(source, raw_anes_data):
    cleaned = source.clean(raw_anes_data)
    result = source.harmonize(cleaned)
    # V201233: [1, 2, 3] → [1.0, 0.0, 0.5]
    assert list(result["social_trust"]) == [1.0, 0.0, 0.5]


def test_authoritarianism_mapping(source, raw_anes_data):
    cleaned = source.clean(raw_anes_data)
    result = source.harmonize(cleaned)
    # V201626: [4, 2, 0] → [1.0, 0.5, 0.0]
    assert list(result["authoritarianism"]) == [1.0, 0.5, 0.0]


def test_big_five_openness_mapping(source, raw_anes_data):
    cleaned = source.clean(raw_anes_data)
    result = source.harmonize(cleaned)
    # V162333: [5, 3, 1] → [1.0, 0.5, 0.0]
    assert list(result["openness"]) == [1.0, 0.5, 0.0]


def test_institutional_confidence_mapping(source, raw_anes_data):
    cleaned = source.clean(raw_anes_data)
    result = source.harmonize(cleaned)
    # V201228: [1, 2, 3] → [1.0, 0.5, 0.0]
    assert list(result["institutional_confidence"]) == [1.0, 0.5, 0.0]


# ---------------------------------------------------------------------------
# clean() behavior
# ---------------------------------------------------------------------------

def test_clean_accepts_dataframe(source, raw_anes_data):
    result = source.clean(raw_anes_data)
    assert isinstance(result, pd.DataFrame)
    assert "V201600" in result.columns


def test_clean_does_not_mutate_input(source, raw_anes_data):
    original_cols = list(raw_anes_data.columns)
    source.clean(raw_anes_data)
    assert list(raw_anes_data.columns) == original_cols


def test_clean_drops_all_na_rows(source):
    df = pd.DataFrame({
        "V201600": [1.0, None],
        "V201626": [None, None],
        "V201233": [None, None],
        "V162333": [None, None],
    })
    cleaned = source.clean(df)
    assert len(cleaned) == 1


# ---------------------------------------------------------------------------
# harmonize() behavior
# ---------------------------------------------------------------------------

def test_harmonize_renames_raw_columns(source, raw_anes_data):
    cleaned = source.clean(raw_anes_data)
    result = source.harmonize(cleaned)
    assert "racial_resentment" in result.columns
    assert "V201600" not in result.columns


def test_match_keys_preserved_after_harmonize(source, raw_anes_data):
    cleaned = source.clean(raw_anes_data)
    result = source.harmonize(cleaned)
    assert list(result["age_bracket"]) == ["18-24", "35-44", "65+"]
    assert list(result["party_id"]) == ["strong_dem", "independent", "strong_rep"]


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
    assert cfg["source"] == "anes"
    assert cfg["match_keys"] == source.match_keys
    assert cfg["variables"] == source.variables_provided
