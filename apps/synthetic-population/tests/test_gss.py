"""Tests for the GSS (General Social Survey) source plugin."""

import pytest
import pandas as pd

from pipeline.sources.gss import (
    GSSSource,
    RELIGION_AFFILIATION_MAP,
    RELIGION_DENOMINATION_MAP,
    RELIGION_ATTENDANCE_MAP,
    RELIGION_BIBLICAL_LITERALISM_MAP,
    RELIGION_IMPORTANCE_MAP,
    SOCIAL_TRUST_MAP,
    INSTITUTIONAL_CONFIDENCE_MAP,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def source():
    return GSSSource()


@pytest.fixture
def raw_gss_data():
    """Minimal GSS-shaped DataFrame covering key columns."""
    return pd.DataFrame({
        "RELIG": [1, 2, 4],           # protestant, catholic, none
        "DENOM": [10, 30, 50],        # baptist, roman catholic, none
        "ATTEND": [7, 4, 0],          # every week, once/month, never
        "BIBLE": [1, 2, 3],           # literal, inspired, ancient book
        "RELITEN": [1, 2, 4],         # strong, somewhat strong, no religion
        "TRUST": [1, 2, 3],           # trust, can't be too careful, depends
        "CONFINAN": [1, 2, 3],        # a great deal, only some, hardly any
        "age_bracket": ["25-34", "45-54", "65+"],
        "sex": ["M", "F", "M"],
        "race": ["white", "black", "white"],
        "education": ["bachelors", "hs_diploma", "graduate"],
    })


# ---------------------------------------------------------------------------
# Metadata tests
# ---------------------------------------------------------------------------

def test_source_name(source):
    assert source.name == "gss"


def test_update_cycle(source):
    assert source.update_cycle == "biennial"


def test_variables_provided(source):
    expected = [
        "religion_affiliation", "religion_denomination", "religion_attendance",
        "religion_biblical_literalism", "religion_importance",
        "social_trust", "institutional_confidence",
    ]
    for var in expected:
        assert var in source.variables_provided, f"Missing variable: {var}"


def test_variables_provided_count(source):
    assert len(source.variables_provided) == 7


# ---------------------------------------------------------------------------
# Match keys
# ---------------------------------------------------------------------------

def test_match_keys(source):
    for key in ["age_bracket", "sex", "race", "education"]:
        assert key in source.match_keys


def test_match_keys_count(source):
    assert len(source.match_keys) == 4


# ---------------------------------------------------------------------------
# Variable mapping tests
# ---------------------------------------------------------------------------

def test_religion_affiliation_mapping(source, raw_gss_data):
    cleaned = source.clean(raw_gss_data)
    result = source.harmonize(cleaned)
    assert list(result["religion_affiliation"]) == ["protestant", "catholic", "none"]


def test_social_trust_mapping(source, raw_gss_data):
    cleaned = source.clean(raw_gss_data)
    result = source.harmonize(cleaned)
    # TRUST: [1, 2, 3] → [1.0, 0.0, 0.5]
    assert list(result["social_trust"]) == [1.0, 0.0, 0.5]


def test_religion_attendance_mapping(source, raw_gss_data):
    cleaned = source.clean(raw_gss_data)
    result = source.harmonize(cleaned)
    # ATTEND: [7, 4, 0] → [0.85, 0.42, 0.0]
    assert result["religion_attendance"].iloc[0] == 0.85
    assert result["religion_attendance"].iloc[1] == 0.42
    assert result["religion_attendance"].iloc[2] == 0.0


def test_institutional_confidence_mapping(source, raw_gss_data):
    cleaned = source.clean(raw_gss_data)
    result = source.harmonize(cleaned)
    # CONFINAN: [1, 2, 3] → [1.0, 0.5, 0.0]
    assert list(result["institutional_confidence"]) == [1.0, 0.5, 0.0]


def test_biblical_literalism_mapping(source, raw_gss_data):
    cleaned = source.clean(raw_gss_data)
    result = source.harmonize(cleaned)
    assert list(result["religion_biblical_literalism"]) == [
        "literal_word", "inspired_not_literal", "ancient_book"
    ]


# ---------------------------------------------------------------------------
# clean() behavior
# ---------------------------------------------------------------------------

def test_clean_accepts_dataframe(source, raw_gss_data):
    result = source.clean(raw_gss_data)
    assert isinstance(result, pd.DataFrame)
    assert "RELIG" in result.columns


def test_clean_does_not_mutate_input(source, raw_gss_data):
    original_cols = list(raw_gss_data.columns)
    source.clean(raw_gss_data)
    assert list(raw_gss_data.columns) == original_cols


def test_clean_drops_all_na_rows(source):
    df = pd.DataFrame({
        "RELIG": [1.0, None],
        "ATTEND": [None, None],
        "TRUST": [None, None],
        "BIBLE": [None, None],
    })
    cleaned = source.clean(df)
    assert len(cleaned) == 1


# ---------------------------------------------------------------------------
# harmonize() behavior
# ---------------------------------------------------------------------------

def test_harmonize_renames_raw_columns(source, raw_gss_data):
    cleaned = source.clean(raw_gss_data)
    result = source.harmonize(cleaned)
    assert "religion_affiliation" in result.columns
    assert "RELIG" not in result.columns


def test_match_keys_preserved_after_harmonize(source, raw_gss_data):
    cleaned = source.clean(raw_gss_data)
    result = source.harmonize(cleaned)
    assert list(result["age_bracket"]) == ["25-34", "45-54", "65+"]
    assert list(result["education"]) == ["bachelors", "hs_diploma", "graduate"]


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
    assert cfg["source"] == "gss"
    assert cfg["match_keys"] == source.match_keys
    assert cfg["variables"] == source.variables_provided
