import pytest
import pandas as pd
from pipeline.fit_model import ModelTrainer


@pytest.fixture
def sample_data():
    """Small dataset for testing SDV fitting."""
    return pd.DataFrame({
        "age_bracket": ["18-24", "25-34", "35-44", "45-54", "55-64", "65+"] * 10,
        "sex": ["M", "F"] * 30,
        "race": ["white", "black", "hispanic", "asian", "white", "white"] * 10,
        "education": ["hs_diploma", "bachelors", "graduate", "some_college", "bachelors", "hs_diploma"] * 10,
        "party_id": ["strong_dem", "lean_dem", "independent", "lean_rep", "strong_rep", "dem"] * 10,
        "ideology": [1, 3, 4, 5, 7, 2] * 10,
        "income": [30000, 55000, 72000, 45000, 90000, 28000] * 10,
    })


def test_fit_model(sample_data):
    trainer = ModelTrainer()
    trainer.fit(sample_data,
                categorical_columns=["age_bracket", "sex", "race", "education", "party_id"],
                numerical_columns=["ideology", "income"])
    assert trainer.model is not None


def test_generate_samples(sample_data):
    trainer = ModelTrainer()
    trainer.fit(sample_data,
                categorical_columns=["age_bracket", "sex", "race", "education", "party_id"],
                numerical_columns=["ideology", "income"])
    samples = trainer.generate(10)
    assert len(samples) == 10
    assert set(samples.columns) == set(sample_data.columns)


def test_save_and_load(sample_data, tmp_path):
    trainer = ModelTrainer()
    trainer.fit(sample_data,
                categorical_columns=["age_bracket", "sex", "race", "education", "party_id"],
                numerical_columns=["ideology", "income"])

    model_path = str(tmp_path / "test_model.pkl")
    trainer.save(model_path)

    trainer2 = ModelTrainer()
    trainer2.load(model_path)
    samples = trainer2.generate(5)
    assert len(samples) == 5


def test_generate_without_fit_raises():
    trainer = ModelTrainer()
    with pytest.raises(RuntimeError):
        trainer.generate(5)


def test_generated_values_in_range(sample_data):
    trainer = ModelTrainer()
    trainer.fit(sample_data,
                categorical_columns=["age_bracket", "sex", "race", "education", "party_id"],
                numerical_columns=["ideology", "income"])
    samples = trainer.generate(20)
    # Categorical values should be from the original set
    for val in samples["sex"].unique():
        assert val in ["M", "F"]
