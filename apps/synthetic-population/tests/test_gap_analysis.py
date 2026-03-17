import pytest
import pandas as pd
from generator.gap_analysis import GapAnalyzer


@pytest.fixture
def marginals():
    return {
        "sex": {"M": 0.48, "F": 0.52},
        "race": {"white": 0.60, "black": 0.13, "hispanic": 0.19, "asian": 0.06, "other": 0.02},
    }


def test_empty_population_all_underrepresented(marginals):
    analyzer = GapAnalyzer(marginals)
    bias = analyzer.analyze(pd.DataFrame(columns=["sex", "race"]))
    assert bias["sex"]["M"] == 2.0
    assert bias["sex"]["F"] == 2.0


def test_overrepresented_gets_low_weight(marginals):
    pop = pd.DataFrame({"sex": ["M"] * 80 + ["F"] * 20, "race": ["white"] * 100})
    analyzer = GapAnalyzer(marginals)
    bias = analyzer.analyze(pop)
    assert bias["sex"]["M"] < 1.0  # 80% actual vs 48% target
    assert bias["sex"]["F"] > 1.0  # 20% actual vs 52% target


def test_underrepresented_gets_high_weight(marginals):
    pop = pd.DataFrame({"sex": ["M"] * 50 + ["F"] * 50, "race": ["white"] * 100})
    analyzer = GapAnalyzer(marginals)
    bias = analyzer.analyze(pop)
    # hispanic not present at all → max weight
    assert bias["race"]["hispanic"] == 2.0


def test_summary_sorted_by_gap(marginals):
    pop = pd.DataFrame({"sex": ["M"] * 50 + ["F"] * 50, "race": ["white"] * 100})
    analyzer = GapAnalyzer(marginals)
    summary = analyzer.summary(pop)
    assert len(summary) > 0
    # First entry should have largest gap
    assert abs(summary[0]["gap"]) >= abs(summary[-1]["gap"])


def test_on_target_weight_is_one(marginals):
    """A perfectly matched distribution should yield weight = 1.0."""
    pop = pd.DataFrame({"sex": ["M"] * 48 + ["F"] * 52, "race": ["white"] * 100})
    analyzer = GapAnalyzer(marginals)
    bias = analyzer.analyze(pop)
    assert bias["sex"]["M"] == pytest.approx(1.0, rel=1e-3)
    assert bias["sex"]["F"] == pytest.approx(1.0, rel=1e-3)


def test_weight_clamped_to_max(marginals):
    """Weight is clamped to 2.0 at the top end."""
    # Only M, so F is 0% actual vs 52% target → ratio = inf → clamped to 2.0
    pop = pd.DataFrame({"sex": ["M"] * 100, "race": ["white"] * 100})
    analyzer = GapAnalyzer(marginals)
    bias = analyzer.analyze(pop)
    assert bias["sex"]["F"] == 2.0


def test_weight_clamped_to_min(marginals):
    """Weight is clamped to 0.1 at the bottom end."""
    # M is 99% actual vs 48% target → ratio ≈ 0.48 → above 0.1 floor, not clamped
    # Use extreme case: variable with 1% target vs 100% actual → ratio = 0.01 → clamp to 0.1
    extreme_marginals = {"sex": {"M": 0.01, "F": 0.99}}
    pop = pd.DataFrame({"sex": ["M"] * 100})
    analyzer = GapAnalyzer(extreme_marginals)
    bias = analyzer.analyze(pop)
    assert bias["sex"]["M"] == pytest.approx(0.1)


def test_summary_fields_present(marginals):
    """Each summary entry has all required fields."""
    pop = pd.DataFrame({"sex": ["M"] * 60 + ["F"] * 40, "race": ["white"] * 100})
    analyzer = GapAnalyzer(marginals)
    summary = analyzer.summary(pop)
    for entry in summary:
        assert "variable" in entry
        assert "value" in entry
        assert "target" in entry
        assert "actual" in entry
        assert "gap" in entry


def test_missing_column_treated_as_empty(marginals):
    """If a target variable is absent from the DataFrame, treat as empty (all weight 2.0)."""
    pop = pd.DataFrame({"sex": ["M"] * 50 + ["F"] * 50})  # no "race" column
    analyzer = GapAnalyzer(marginals)
    bias = analyzer.analyze(pop)
    for val in marginals["race"]:
        assert bias["race"][val] == 2.0


def test_priority_weighted_returns_dict_structure(marginals):
    """analyze() always returns a nested dict keyed by variable then value."""
    pop = pd.DataFrame({"sex": ["M"] * 30 + ["F"] * 70, "race": ["white"] * 100})
    analyzer = GapAnalyzer(marginals)
    bias = analyzer.analyze(pop)
    assert isinstance(bias, dict)
    for var in marginals:
        assert var in bias
        assert isinstance(bias[var], dict)
        for val in marginals[var]:
            assert val in bias[var]
            assert isinstance(bias[var][val], float)
