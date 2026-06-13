import pytest
import json
import pandas as pd
from pathlib import Path
from pipeline.fit_model import ModelTrainer
from generator.generate import ProfileGenerator


@pytest.fixture
def fitted_model(tmp_path):
    """Create and save a fitted SDV model for testing."""
    data = pd.DataFrame({
        "age": list(range(20, 80)) * 2,
        "age_bracket": (["18-24"] * 5 + ["25-34"] * 20 + ["35-44"] * 20 + ["45-54"] * 20 + ["55-64"] * 20 + ["65+"] * 15 + ["18-24"] * 5 + ["25-34"] * 15)[:120],
        "sex": ["M", "F"] * 60,
        "race": ["white"] * 60 + ["black"] * 20 + ["hispanic"] * 20 + ["asian"] * 10 + ["other"] * 10,
        "education": ["hs_diploma", "bachelors", "graduate", "some_college", "bachelors", "hs_diploma"] * 20,
        "state": ["MI", "OH", "GA", "TX", "CA", "NY"] * 20,
        "party_id": ["strong_dem", "lean_dem", "independent", "lean_rep", "strong_rep", "dem"] * 20,
        "religion_affiliation": ["evangelical", "mainline", "none", "catholic", "none", "evangelical"] * 20,
        "religion_attendance": ["weekly", "monthly", "never", "weekly", "never", "weekly"] * 20,
        "urban_rural": ["rural", "suburban", "urban", "rural", "urban", "suburban"] * 20,
        "income_source": ["wages", "wages", "wages", "self_employment", "wages", "wages"] * 20,
        "income_bracket": ["25-50k", "50-75k", "75-100k", "50-75k", "100-150k", "25-50k"] * 20,
        "income": [35000, 60000, 85000, 55000, 120000, 30000] * 20,
        "marital_status": ["married", "divorced", "never_married", "married", "married", "widowed"] * 20,
        "occupation": ["mechanic", "teacher", "engineer", "nurse", "manager", "retired"] * 20,
        "children_count": [2, 1, 0, 3, 1, 0] * 20,
    })
    # Trim to exactly 120 rows
    data = data.head(120)

    trainer = ModelTrainer()
    categorical = ["age_bracket", "sex", "race", "education", "state", "party_id",
                   "religion_affiliation", "religion_attendance", "urban_rural",
                   "income_source", "income_bracket", "marital_status", "occupation"]
    trainer.fit(data, categorical_columns=categorical, numerical_columns=["age", "income", "children_count"])

    model_path = str(tmp_path / "test_model.pkl")
    trainer.save(model_path)
    return model_path


@pytest.fixture
def registry_path(tmp_path):
    return str(tmp_path / "profiles" / "registry.json")


def test_generate_batch(fitted_model, registry_path):
    gen = ProfileGenerator(fitted_model, registry_path)
    profiles = gen.generate_batch(5, batch_name="test-batch")
    assert len(profiles) == 5
    assert all("profile_id" in p for p in profiles)
    assert all("batch_id" in p for p in profiles)
    assert all("backstory" in p for p in profiles)


def test_profiles_saved_to_registry(fitted_model, registry_path):
    gen = ProfileGenerator(fitted_model, registry_path)
    gen.generate_batch(5)
    assert Path(registry_path).exists()
    with open(registry_path) as f:
        saved = json.load(f)
    assert len(saved) == 5


def test_incremental_generation(fitted_model, registry_path):
    gen = ProfileGenerator(fitted_model, registry_path)
    gen.generate_batch(5, batch_name="batch-1")
    gen2 = ProfileGenerator(fitted_model, registry_path)
    gen2.generate_batch(5, batch_name="batch-2")
    with open(registry_path) as f:
        saved = json.load(f)
    assert len(saved) == 10


def test_archetype_assigned(fitted_model, registry_path):
    gen = ProfileGenerator(fitted_model, registry_path)
    profiles = gen.generate_batch(10)
    assert all("archetype_id" in p for p in profiles)
    # At least some should have archetype IDs
    assert any(p["archetype_id"] is not None for p in profiles)
