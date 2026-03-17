"""Tests for plausibility filter — the Reddit roast test."""
from generator.plausibility import fix_profile, check_profile


def test_negative_income_clamped():
    p = fix_profile({"age": 40, "income": -5000})
    assert p["income"] >= 0


def test_20yo_cant_have_3_kids():
    p = fix_profile({"age": 20, "children_count": 3, "marital_status": "married"})
    assert p["children_count"] <= 2


def test_20yo_not_in_management():
    p = fix_profile({"age": 20, "occupation": "management", "education": "some_college"})
    assert p["occupation"] != "management"


def test_18yo_cant_be_married():
    p = fix_profile({"age": 18, "marital_status": "married", "children_count": 0})
    assert p["marital_status"] == "never_married"


def test_22yo_cant_have_graduate_degree():
    p = fix_profile({"age": 22, "education": "graduate"})
    assert p["education"] != "graduate"


def test_25yo_cant_be_widowed():
    p = fix_profile({"age": 25, "marital_status": "widowed"})
    assert p["marital_status"] != "widowed"


def test_30yo_retirement_income_fixed():
    p = fix_profile({"age": 30, "income_source": "retirement"})
    assert p["income_source"] != "retirement"


def test_65yo_not_working_gets_retirement():
    p = fix_profile({"age": 67, "employment_status": "not_in_labor_force", "income_source": "wages"})
    assert p["income_source"] == "retirement"


def test_young_high_income_capped():
    p = fix_profile({"age": 20, "income": 200000, "education": "some_college"})
    assert p["income"] < 60000


def test_household_size_consistent_with_kids():
    p = fix_profile({"age": 35, "children_count": 3, "household_size": 1, "marital_status": "married"})
    assert p["household_size"] >= 5  # self + spouse + 3 kids


def test_check_returns_flags():
    flags = check_profile({"age": 20, "education": "graduate", "children_count": 4,
                           "marital_status": "married", "occupation": "management", "income": -5000})
    assert len(flags) >= 3  # multiple issues


def test_plausible_profile_no_flags():
    flags = check_profile({"age": 45, "education": "bachelors", "children_count": 2,
                           "marital_status": "married", "occupation": "professional",
                           "income": 85000, "income_source": "wages",
                           "employment_status": "employed"})
    assert len(flags) == 0


def test_fix_preserves_plausible_profile():
    original = {"age": 45, "education": "bachelors", "children_count": 2,
                "marital_status": "married", "occupation": "professional",
                "income": 85000, "income_source": "wages"}
    fixed = fix_profile(original.copy())
    assert fixed["education"] == "bachelors"
    assert fixed["children_count"] == 2
    assert fixed["marital_status"] == "married"
    assert fixed["income"] == 85000


def test_19yo_divorced_becomes_never_married():
    p = fix_profile({"age": 19, "marital_status": "divorced"})
    assert p["marital_status"] == "never_married"


def test_income_bracket_recalculated():
    p = fix_profile({"age": 40, "income": -30000, "income_bracket": "150k+"})
    assert p["income"] == 30000
    assert p["income_bracket"] == "25-50k"  # abs(-30000) = 30000
