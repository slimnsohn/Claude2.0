import pytest
import pandas as pd
import numpy as np
from pipeline.fuse import StatisticalMatcher


@pytest.fixture
def backbone():
    """ACS-like backbone with demographics only."""
    return pd.DataFrame({
        "age_bracket": ["25-34", "45-54", "25-34", "65+"],
        "sex": ["M", "F", "F", "M"],
        "race": ["white", "white", "black", "hispanic"],
        "education": ["some_college", "bachelors", "graduate", "hs_diploma"],
        "income_bracket": ["50-75k", "50-75k", "75-100k", "25-50k"],
        "state": ["MI", "OH", "GA", "TX"],
        "urban_rural": ["rural", "suburban", "urban", "rural"],
    })


@pytest.fixture
def donor():
    """CES-like donor with demographics + political variables."""
    return pd.DataFrame({
        "age_bracket": ["25-34", "25-34", "45-54", "45-54", "65+", "65+"],
        "sex": ["M", "M", "F", "F", "M", "M"],
        "race": ["white", "white", "white", "white", "hispanic", "hispanic"],
        "education": ["some_college", "some_college", "bachelors", "bachelors", "hs_diploma", "hs_diploma"],
        "party_id": ["lean_rep", "strong_rep", "lean_dem", "dem", "dem", "lean_rep"],
        "ideology": [5, 7, 3, 2, 3, 5],
    })


def test_match_returns_correct_shape(backbone, donor):
    matcher = StatisticalMatcher(match_keys=["age_bracket", "sex", "race", "education"])
    result = matcher.match(backbone, donor, variables=["party_id", "ideology"])
    assert len(result) == len(backbone)
    assert "party_id" in result.columns
    assert "ideology" in result.columns


def test_match_preserves_backbone_columns(backbone, donor):
    matcher = StatisticalMatcher(match_keys=["age_bracket", "sex", "race", "education"])
    result = matcher.match(backbone, donor, variables=["party_id", "ideology"])
    for col in backbone.columns:
        assert col in result.columns


def test_match_uses_nearest_donor(backbone, donor):
    np.random.seed(42)
    matcher = StatisticalMatcher(match_keys=["age_bracket", "sex", "race", "education"])
    result = matcher.match(backbone, donor, variables=["party_id"])
    # Row 0: 25-34, M, white, some_college → should match donor rows 0 or 1
    assert result["party_id"].iloc[0] in ["lean_rep", "strong_rep"]


def test_match_handles_no_exact_match(backbone, donor):
    """When no exact match exists, falls back to closest partial match."""
    matcher = StatisticalMatcher(match_keys=["age_bracket", "sex", "race", "education"])
    result = matcher.match(backbone, donor, variables=["party_id"])
    # Row 2: 25-34, F, black, graduate — no exact match in donor
    assert pd.notna(result["party_id"].iloc[2])
