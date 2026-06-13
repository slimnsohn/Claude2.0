import pytest
import pandas as pd
from pipeline.sources.acs_pums import ACSPumsSource


@pytest.fixture
def source():
    return ACSPumsSource()


@pytest.fixture
def raw_pums_data():
    """Simulated raw PUMS data with real PUMS column names and codes."""
    return pd.DataFrame({
        "AGEP": [34, 52, 28, 67],
        "SEX": [1, 2, 2, 1],
        "RAC1P": [1, 1, 2, 6],
        "HISP": [1, 1, 1, 2],
        "SCHL": [19, 21, 22, 16],
        "PINCP": [52000, 68000, 85000, 35000],
        "MAR": [1, 1, 5, 3],
        "ST": [26, 39, 13, 48],
        "MIL": [4, 4, 4, 2],
        "DIS": [2, 2, 2, 1],
        "CIT": [1, 1, 1, 4],
        "ENG": [None, None, None, 2],
        "NP": [4, 3, 1, 2],
        "JWTRNS": [1, 1, 6, None],
        "ESR": [1, 1, 1, 6],
        "OCCP": ["4720", "3255", "2100", None],
        "INDP": ["7860", "8190", "6170", None],
        "HINS1": [2, 1, 1, 2],
        "TEN": [1, 1, 3, 1],
        "PWGTP": [45, 62, 38, 55],
    })


def test_source_metadata(source):
    assert source.name == "acs_pums"
    assert "age" in source.variables_provided
    assert "race" in source.variables_provided
    assert source.update_cycle == "annual"


def test_harmonize_maps_sex(source, raw_pums_data):
    result = source.harmonize(source.clean_dataframe(raw_pums_data))
    assert list(result["sex"]) == ["M", "F", "F", "M"]


def test_harmonize_maps_race_with_hispanic_override(source, raw_pums_data):
    result = source.harmonize(source.clean_dataframe(raw_pums_data))
    # Row 3 (index 3): RAC1P=6 but HISP=2 (Hispanic) → "hispanic"
    assert result["race"].iloc[3] == "hispanic"


def test_harmonize_maps_education(source, raw_pums_data):
    result = source.harmonize(source.clean_dataframe(raw_pums_data))
    expected = ["some_college", "bachelors", "graduate", "hs_diploma"]
    assert list(result["education"]) == expected


def test_harmonize_computes_age_bracket(source, raw_pums_data):
    result = source.harmonize(source.clean_dataframe(raw_pums_data))
    assert result["age_bracket"].iloc[0] == "25-34"
    assert result["age_bracket"].iloc[3] == "65+"


def test_harmonize_preserves_person_weight(source, raw_pums_data):
    result = source.harmonize(source.clean_dataframe(raw_pums_data))
    assert "acs_pums:person_weight" in result.columns


# --- Additional coverage ---

def test_harmonize_maps_income_bracket(source, raw_pums_data):
    result = source.harmonize(source.clean_dataframe(raw_pums_data))
    # PINCP: 52000 → "50-75k", 68000 → "50-75k", 85000 → "75-100k", 35000 → "25-50k"
    assert list(result["income_bracket"]) == ["50-75k", "50-75k", "75-100k", "25-50k"]


def test_harmonize_maps_state_fips(source, raw_pums_data):
    result = source.harmonize(source.clean_dataframe(raw_pums_data))
    # ST: 26→MI, 39→OH, 13→GA, 48→TX
    assert list(result["state"]) == ["MI", "OH", "GA", "TX"]


def test_harmonize_maps_marital_status(source, raw_pums_data):
    result = source.harmonize(source.clean_dataframe(raw_pums_data))
    # MAR: 1→married, 1→married, 5→never_married, 3→divorced
    assert list(result["marital_status"]) == ["married", "married", "never_married", "divorced"]


def test_harmonize_maps_veteran_status(source, raw_pums_data):
    result = source.harmonize(source.clean_dataframe(raw_pums_data))
    # MIL: 4,4,4,2 → non_veteran, non_veteran, non_veteran, veteran
    assert result["veteran_status"].iloc[3] == "veteran"
    assert result["veteran_status"].iloc[0] == "non_veteran"


def test_harmonize_maps_disability(source, raw_pums_data):
    result = source.harmonize(source.clean_dataframe(raw_pums_data))
    # DIS: 2,2,2,1 → False, False, False, True
    assert result["disability"].iloc[3] == True  # noqa: E712 — numpy bool needs == not is
    assert result["disability"].iloc[0] == False  # noqa: E712


def test_harmonize_maps_health_insurance(source, raw_pums_data):
    result = source.harmonize(source.clean_dataframe(raw_pums_data))
    # HINS1: 2,1,1,2 → False, True, True, False
    assert list(result["health_insurance"]) == [False, True, True, False]


def test_clean_dataframe_filters_minors(source):
    df = pd.DataFrame({
        "AGEP": [16, 18, 25, 17],
        "SEX": [1, 2, 1, 2],
        "RAC1P": [1, 1, 1, 1],
        "HISP": [1, 1, 1, 1],
        "SCHL": [10, 16, 19, 8],
        "PINCP": [0, 20000, 45000, 0],
        "MAR": [5, 5, 5, 5],
        "ST": [26, 26, 26, 26],
        "PWGTP": [10, 15, 20, 12],
    })
    cleaned = source.clean_dataframe(df)
    assert len(cleaned) == 2
    assert all(cleaned["AGEP"] >= 18)


def test_harmonize_non_hispanic_race_preserved(source, raw_pums_data):
    result = source.harmonize(source.clean_dataframe(raw_pums_data))
    # Row 0: RAC1P=1, HISP=1 (not Hispanic) → "white"
    assert result["race"].iloc[0] == "white"
    # Row 2: RAC1P=2, HISP=1 → "black"
    assert result["race"].iloc[2] == "black"


def test_harmonize_person_weight_values(source, raw_pums_data):
    result = source.harmonize(source.clean_dataframe(raw_pums_data))
    assert list(result["acs_pums:person_weight"]) == [45, 62, 38, 55]


def test_source_variables_provided_complete(source):
    expected = [
        "age", "age_bracket", "sex", "race", "education", "income",
        "income_bracket", "marital_status", "state", "veteran_status",
        "disability", "citizenship", "language", "household_size",
        "employment_status", "homeownership", "health_insurance", "commute_mode",
    ]
    for v in expected:
        assert v in source.variables_provided, f"Missing variable: {v}"


def test_match_config(source):
    config = source.match_config()
    assert config["source"] == "acs_pums"
    assert "age_bracket" in config["match_keys"]
    assert "race" in config["match_keys"]


def test_download_raises_not_implemented(source):
    with pytest.raises(NotImplementedError):
        source.download()
