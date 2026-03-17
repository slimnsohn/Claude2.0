"""Tests for the CES (Cooperative Election Study) source plugin."""

import pytest
import pandas as pd

from pipeline.sources.ces import CESSource, PARTY_ID_MAP, IDEOLOGY_5PT_MAP, VOTE_2020_MAP, VOTE_2024_MAP, POLICY_MAP


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def source():
    return CESSource()


@pytest.fixture
def raw_ces_data():
    """Minimal CES-shaped DataFrame covering all key columns."""
    return pd.DataFrame({
        "pid7": [1, 4, 7],
        "ideo5": [1, 3, 5],
        "CC20_410": [1, 2, 4],   # vote 2020: biden, trump, did_not_vote
        "CC24_410": [1, 4, 2],   # vote 2024: harris, did_not_vote, trump
        "CC20_330a": [1, 2, 4],  # gun control policy: 1.0, 0.67, 0.0
        "CC20_321": [1, 2, 3],   # abortion
        "CC20_331": [4, 3, 1],   # immigration
        "age_bracket": ["25-34", "45-54", "65+"],
        "sex": ["M", "F", "M"],
        "race": ["black", "white", "white"],
        "education": ["graduate", "bachelors", "hs_diploma"],
        "income_bracket": ["50-75k", "100-150k", "25-50k"],
        "state": ["TX", "CA", "NY"],
        "urban_rural": ["urban", "suburban", "rural"],
    })


# ---------------------------------------------------------------------------
# Metadata tests
# ---------------------------------------------------------------------------

def test_source_metadata(source):
    assert source.name == "ces"
    assert "party_id" in source.variables_provided
    assert "ideology" in source.variables_provided
    assert "vote_2020" in source.variables_provided
    assert "vote_2024" in source.variables_provided
    assert source.update_cycle == "election_year"


def test_variables_provided_contains_all_policy_positions(source):
    policy_vars = [
        "abortion", "gun_control", "immigration", "climate_policy",
        "healthcare_system", "government_spending", "trade_policy",
        "criminal_justice", "education_policy", "social_security",
        "marijuana", "minimum_wage", "foreign_policy", "tax_policy",
        "tech_regulation",
    ]
    for var in policy_vars:
        assert var in source.variables_provided, f"Missing policy variable: {var}"


def test_variables_provided_count(source):
    # 4 core + 15 policy = 19 total
    assert len(source.variables_provided) == 19


# ---------------------------------------------------------------------------
# Match keys
# ---------------------------------------------------------------------------

def test_match_keys(source):
    for key in ["age_bracket", "sex", "race", "education", "income_bracket", "state", "urban_rural"]:
        assert key in source.match_keys


def test_match_keys_count(source):
    assert len(source.match_keys) == 7


# ---------------------------------------------------------------------------
# Party ID mapping
# ---------------------------------------------------------------------------

def test_party_id_mapping(source, raw_ces_data):
    cleaned = source.clean(raw_ces_data)
    result = source.harmonize(cleaned)
    assert list(result["party_id"]) == ["strong_dem", "independent", "strong_rep"]


def test_party_id_full_scale(source):
    df = pd.DataFrame({
        "pid7": [1, 2, 3, 4, 5, 6, 7],
        "ideo5": [1, 1, 1, 1, 1, 1, 1],
    })
    cleaned = source.clean(df)
    result = source.harmonize(cleaned)
    assert list(result["party_id"]) == [
        "strong_dem", "dem", "lean_dem", "independent", "lean_rep", "rep", "strong_rep"
    ]


# ---------------------------------------------------------------------------
# Ideology mapping
# ---------------------------------------------------------------------------

def test_ideology_5pt_mapping(source):
    df = pd.DataFrame({
        "pid7": [4, 4, 4, 4, 4],
        "ideo5": [1, 2, 3, 4, 5],
    })
    cleaned = source.clean(df)
    result = source.harmonize(cleaned)
    assert list(result["ideology"]) == [
        "very_liberal", "liberal", "moderate", "conservative", "very_conservative"
    ]


def test_ideology_moderate_center(source, raw_ces_data):
    cleaned = source.clean(raw_ces_data)
    result = source.harmonize(cleaned)
    # ideo5=3 maps to moderate
    assert result["ideology"].iloc[1] == "moderate"


# ---------------------------------------------------------------------------
# Vote choice mapping
# ---------------------------------------------------------------------------

def test_vote_2020_mapping(source, raw_ces_data):
    cleaned = source.clean(raw_ces_data)
    result = source.harmonize(cleaned)
    assert list(result["vote_2020"]) == ["biden", "trump", "did_not_vote"]


def test_vote_2024_mapping(source, raw_ces_data):
    cleaned = source.clean(raw_ces_data)
    result = source.harmonize(cleaned)
    assert list(result["vote_2024"]) == ["harris", "did_not_vote", "trump"]


def test_vote_2020_all_options(source):
    df = pd.DataFrame({
        "pid7": [1, 1, 1, 1],
        "ideo5": [1, 1, 1, 1],
        "CC20_410": [1, 2, 3, 4],
    })
    cleaned = source.clean(df)
    result = source.harmonize(cleaned)
    assert list(result["vote_2020"]) == ["biden", "trump", "other", "did_not_vote"]


def test_vote_2024_all_options(source):
    df = pd.DataFrame({
        "pid7": [1, 1, 1, 1],
        "ideo5": [1, 1, 1, 1],
        "CC24_410": [1, 2, 3, 4],
    })
    cleaned = source.clean(df)
    result = source.harmonize(cleaned)
    assert list(result["vote_2024"]) == ["harris", "trump", "other", "did_not_vote"]


# ---------------------------------------------------------------------------
# Policy position mappings
# ---------------------------------------------------------------------------

def test_policy_map_values():
    assert POLICY_MAP[1] == 1.0
    assert POLICY_MAP[2] == 0.67
    assert POLICY_MAP[3] == 0.33
    assert POLICY_MAP[4] == 0.0


def test_gun_control_policy_mapping(source, raw_ces_data):
    cleaned = source.clean(raw_ces_data)
    result = source.harmonize(cleaned)
    # CC20_330a: [1, 2, 4] → [1.0, 0.67, 0.0]
    assert list(result["gun_control"]) == [1.0, 0.67, 0.0]


def test_abortion_policy_mapping(source, raw_ces_data):
    cleaned = source.clean(raw_ces_data)
    result = source.harmonize(cleaned)
    # CC20_321: [1, 2, 3] → [1.0, 0.67, 0.33]
    assert list(result["abortion"]) == [1.0, 0.67, 0.33]


def test_immigration_policy_mapping(source, raw_ces_data):
    cleaned = source.clean(raw_ces_data)
    result = source.harmonize(cleaned)
    # CC20_331: [4, 3, 1] → [0.0, 0.33, 1.0]
    assert list(result["immigration"]) == [0.0, 0.33, 1.0]


# ---------------------------------------------------------------------------
# Match key pass-through in harmonize()
# ---------------------------------------------------------------------------

def test_match_keys_preserved_after_harmonize(source, raw_ces_data):
    cleaned = source.clean(raw_ces_data)
    result = source.harmonize(cleaned)
    assert list(result["age_bracket"]) == ["25-34", "45-54", "65+"]
    assert list(result["sex"]) == ["M", "F", "M"]
    assert list(result["race"]) == ["black", "white", "white"]
    assert list(result["education"]) == ["graduate", "bachelors", "hs_diploma"]
    assert list(result["state"]) == ["TX", "CA", "NY"]


# ---------------------------------------------------------------------------
# clean() behavior
# ---------------------------------------------------------------------------

def test_clean_accepts_dataframe(source, raw_ces_data):
    """clean() should accept a DataFrame directly (not just file paths)."""
    result = source.clean(raw_ces_data)
    assert isinstance(result, pd.DataFrame)
    # clean() preserves raw CES column names; harmonize() does the translation
    assert "pid7" in result.columns


def test_clean_preserves_raw_column_names(source, raw_ces_data):
    """clean() must not rename columns — harmonize() handles that."""
    cleaned = source.clean(raw_ces_data)
    assert "pid7" in cleaned.columns
    assert "ideo5" in cleaned.columns


def test_harmonize_translates_pid7_to_party_id(source, raw_ces_data):
    cleaned = source.clean(raw_ces_data)
    result = source.harmonize(cleaned)
    assert "party_id" in result.columns
    assert "pid7" not in result.columns


def test_harmonize_translates_ideo5_to_ideology(source, raw_ces_data):
    cleaned = source.clean(raw_ces_data)
    result = source.harmonize(cleaned)
    assert "ideology" in result.columns
    assert "ideo5" not in result.columns


def test_clean_drops_all_na_political_rows(source):
    df = pd.DataFrame({
        "pid7": [1, None],
        "ideo5": [None, None],
        "CC20_410": [None, None],
        "CC24_410": [None, None],
    })
    cleaned = source.clean(df)
    # Row 0 has pid7=1, so it survives. Row 1 is all-null across political cols.
    assert len(cleaned) == 1


def test_clean_does_not_mutate_input(source, raw_ces_data):
    original_cols = list(raw_ces_data.columns)
    source.clean(raw_ces_data)
    assert list(raw_ces_data.columns) == original_cols


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
    assert cfg["source"] == "ces"
    assert cfg["match_keys"] == source.match_keys
    assert cfg["variables"] == source.variables_provided


# ---------------------------------------------------------------------------
# Integration: clean → harmonize round-trip
# ---------------------------------------------------------------------------

def test_full_pipeline_round_trip(source, raw_ces_data):
    cleaned = source.clean(raw_ces_data)
    result = source.harmonize(cleaned)

    assert len(result) == 3
    # Core political columns present
    for col in ["party_id", "ideology", "vote_2020", "vote_2024"]:
        assert col in result.columns
    # All match keys present
    for key in source.match_keys:
        assert key in result.columns
    # No raw CES coded column names bleed through
    for raw_col in ["pid7", "ideo5", "CC20_410", "CC24_410"]:
        assert raw_col not in result.columns
