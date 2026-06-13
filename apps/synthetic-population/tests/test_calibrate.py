import pytest
import pandas as pd
import numpy as np
from pipeline.calibrate import IPFCalibrator


@pytest.fixture
def population():
    """Population skewed toward male and white."""
    np.random.seed(42)
    n = 200
    return pd.DataFrame({
        "sex": np.random.choice(["M", "F"], size=n, p=[0.7, 0.3]),
        "race": np.random.choice(["white", "black", "hispanic", "asian"], size=n, p=[0.8, 0.1, 0.05, 0.05]),
        "education": np.random.choice(["hs_diploma", "bachelors", "graduate"], size=n, p=[0.5, 0.3, 0.2]),
    })


@pytest.fixture
def marginals():
    return {
        "sex": {"M": 0.48, "F": 0.52},
        "race": {"white": 0.60, "black": 0.13, "hispanic": 0.19, "asian": 0.06},
    }


def test_calibration_adjusts_marginals(population, marginals):
    cal = IPFCalibrator(tolerance=0.02)
    result = cal.calibrate(population, marginals)
    assert "_weight" in result.columns
    # Check sex marginals within tolerance
    male_prop = result.loc[result["sex"] == "M", "_weight"].sum()
    assert abs(male_prop - 0.48) < 0.02


def test_calibration_weights_sum_to_one(population, marginals):
    cal = IPFCalibrator()
    result = cal.calibrate(population, marginals)
    assert abs(result["_weight"].sum() - 1.0) < 0.001


def test_check_marginals_reports_diffs(population, marginals):
    cal = IPFCalibrator()
    result = cal.calibrate(population, marginals)
    report = cal.check_marginals(result, marginals)
    for var in marginals:
        for val in marginals[var]:
            assert abs(report[var][val]["diff"]) < 0.02


def test_calibration_preserves_correlations(population, marginals):
    """Calibration adjusts weights but doesn't change the underlying data."""
    cal = IPFCalibrator()
    result = cal.calibrate(population, marginals)
    # Original data unchanged
    assert list(result["sex"]) == list(population["sex"])
    assert list(result["race"]) == list(population["race"])
