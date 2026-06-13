import pytest
import pandas as pd
from pathlib import Path

@pytest.fixture
def sample_demographics():
    """Minimal demographic records for testing."""
    return pd.DataFrame({
        "age": [34, 52, 28, 67, 41],
        "sex": ["M", "F", "F", "M", "F"],
        "race": ["white", "white", "black", "hispanic", "asian"],
        "education": ["some_college", "bachelors", "graduate", "hs_diploma", "bachelors"],
        "income_bracket": ["50-75k", "50-75k", "75-100k", "25-50k", "100-150k"],
        "marital_status": ["married", "married", "never_married", "widowed", "married"],
        "state": ["MI", "OH", "GA", "TX", "CA"],
        "urban_rural": ["rural", "suburban", "urban", "rural", "urban"],
        "party_id": ["lean_rep", "lean_rep", "strong_dem", "dem", "lean_dem"],
        "religion_affiliation": ["evangelical", "mainline", "none", "catholic", "none"],
        "religion_attendance": ["weekly", "monthly", "never", "weekly", "never"],
    })

@pytest.fixture
def data_dir(tmp_path):
    """Temporary data directory structure."""
    for subdir in ["models", "profiles", "events", "polls"]:
        (tmp_path / subdir).mkdir()
    return tmp_path
