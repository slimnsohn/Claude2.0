import random

import numpy as np
import pandas as pd
import pytest

from generator.ces_harmonize import harmonize_ces
from generator.population_builder import (
    CENSUS_TARGETS, KEY_VARS, compute_targets, rake_weights,
    respondent_to_profile, balance_report, BalanceError, check_balance,
)


def _fixture_ces(n=2000, seed=7):
    """Raw-format CES-like frame, deliberately skewed (too many strong_dem, too few strong_rep)."""
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "caseid": np.arange(1, n + 1),
        "pid7": rng.choice([1, 2, 3, 4, 5, 6, 7, 8], n, p=[.30, .12, .08, .15, .08, .10, .07, .10]),
        "gender4": rng.choice([1, 2, 3, 4], n, p=[.48, .48, .02, .02]),
        "race": rng.choice([1, 2, 3, 4, 5, 6, 7, 8], n, p=[.70, .08, .10, .04, .03, .02, .02, .01]),
        "educ": rng.choice([1, 2, 3, 4, 5, 6], n, p=[.05, .20, .15, .15, .28, .17]),
        "birthyr": rng.integers(1940, 2007, n),
        "urbancity": rng.choice([1, 2, 3, 4], n, p=[.30, .30, .15, .25]),
        "faminc_new": rng.integers(1, 17, n),
        "inputstate": rng.choice([6, 12, 36, 48], n),
        "ideo5": rng.choice([1, 2, 3, 4, 5], n),
        "CC24_410": rng.choice([1, 2, 3, 4], n),
        "religpew": rng.choice([1, 2, 9], n),
        "pew_bornagain": rng.choice([1, 2], n),
        "pew_churatd": rng.choice([1, 2, 3, 4, 5, 6], n),
    })


def test_harmonize_adds_profile_fields():
    df = harmonize_ces(_fixture_ces())
    for col in ["party_id", "sex", "race_h", "education", "age_bracket", "urban_rural"]:
        assert col in df.columns
    assert set(df["party_id"].dropna().unique()) <= {
        "strong_dem", "dem", "lean_dem", "independent", "lean_rep", "rep", "strong_rep"}
    assert str(df["age_bracket"].dtype) in ("object", "category")


def test_rake_weights_matches_marginals():
    df = harmonize_ces(_fixture_ces()).dropna(subset=KEY_VARS)
    targets = compute_targets(df)
    w = rake_weights(df, targets, KEY_VARS, iterations=30)
    assert w.shape[0] == len(df)
    assert abs(w.sum() - 1.0) < 1e-9
    # Weighted marginal for each var must be within 1% of target
    df = df.reset_index(drop=True)
    for var in KEY_VARS:
        for val, tgt in targets[var].items():
            mask = (df[var] == val).to_numpy()
            actual = w[mask].sum()
            if mask.any():
                assert abs(actual - tgt) < 0.01, f"{var}={val}"


def test_respondent_to_profile_fields():
    df = harmonize_ces(_fixture_ces())
    row = df.iloc[0]
    p = respondent_to_profile(row, batch_id="test-batch", rng=random.Random(1))
    assert p["ces_row_id"] == int(row["caseid"])
    assert p["batch_id"] == "test-batch"
    assert p["drift_log"] == []
    assert p["beliefs"] == {}
    assert p["party_id"] in {"strong_dem", "dem", "lean_dem", "independent",
                             "lean_rep", "rep", "strong_rep"}
    assert isinstance(p["income"], int)
    assert len(p["profile_id"]) == 8
    assert isinstance(p["backstory"], str) and len(p["backstory"]) > 20


def test_respondent_to_profile_deterministic_with_seed():
    df = harmonize_ces(_fixture_ces())
    row = df.iloc[3]
    a = respondent_to_profile(row, "b", rng=random.Random(42))
    b = respondent_to_profile(row, "b", rng=random.Random(42))
    for k in ("profile_id", "created_at", "updated_at"):
        a.pop(k); b.pop(k)
    assert a == b


def test_balance_report_and_gate():
    profiles = [{"sex": "M", "race": "white", "education": "bachelors",
                 "age_bracket": "35-44", "party_id": "dem", "urban_rural": "urban"}] * 100
    targets = {"sex": {"M": 0.49, "F": 0.51}}
    report = balance_report(profiles, targets)
    assert report["max_gap"] > 0.03
    with pytest.raises(BalanceError):
        check_balance(report, tolerance=0.03)
