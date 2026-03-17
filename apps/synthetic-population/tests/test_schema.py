"""Tests for the standard schema and validation logic."""

from schema.standard import (
    STANDARD_SCHEMA, DEMOGRAPHICS, SOCIOECONOMICS, ECONOMIC_IDENTITY,
    FINANCIAL_BEHAVIOR, FINANCIAL_SOPHISTICATION, GEOGRAPHY, POLITICAL,
    POLICY_POSITIONS, PSYCHOLOGY, RELIGION, MEDIA_DIET, SCIENCE_HEALTH,
    ORIGIN_MOBILITY, SYSTEM_METADATA
)
from schema.validation import validate_profile, ValidationError


def test_schema_has_all_categories():
    categories = [
        DEMOGRAPHICS, SOCIOECONOMICS, ECONOMIC_IDENTITY, FINANCIAL_BEHAVIOR,
        FINANCIAL_SOPHISTICATION, GEOGRAPHY, POLITICAL, POLICY_POSITIONS,
        PSYCHOLOGY, RELIGION, MEDIA_DIET, SCIENCE_HEALTH, ORIGIN_MOBILITY,
        SYSTEM_METADATA
    ]
    total = sum(len(c) for c in categories)
    assert total >= 142, f"Expected 142+ variables, got {total}"


def test_each_variable_has_type_and_allowed_values():
    for name, spec in STANDARD_SCHEMA.items():
        assert "type" in spec, f"{name} missing type"
        assert spec["type"] in ("str", "int", "float", "bool"), f"{name} has invalid type"
        if spec["type"] == "str":
            assert "values" in spec, f"{name} (str) missing allowed values"


def test_validate_profile_accepts_valid():
    profile = {
        "age": 34, "sex": "M", "race": "white", "education": "some_college",
        "state": "MI", "party_id": "lean_rep", "urban_rural": "rural",
        "religion_affiliation": "evangelical", "religion_attendance": "weekly",
        "income_bracket": "50-75k", "marital_status": "married",
    }
    errors = validate_profile(profile, partial=True)
    assert errors == []


def test_validate_profile_rejects_invalid_values():
    profile = {"sex": "X", "race": "martian"}
    errors = validate_profile(profile, partial=True)
    assert len(errors) == 2


def test_validate_profile_rejects_wrong_type():
    profile = {"age": "thirty-four"}
    errors = validate_profile(profile, partial=True)
    assert len(errors) == 1


def test_standard_schema_is_merged():
    """STANDARD_SCHEMA should contain all variables from all categories."""
    all_keys = set()
    for cat in [
        DEMOGRAPHICS, SOCIOECONOMICS, ECONOMIC_IDENTITY, FINANCIAL_BEHAVIOR,
        FINANCIAL_SOPHISTICATION, GEOGRAPHY, POLITICAL, POLICY_POSITIONS,
        PSYCHOLOGY, RELIGION, MEDIA_DIET, SCIENCE_HEALTH, ORIGIN_MOBILITY,
        SYSTEM_METADATA
    ]:
        all_keys.update(cat.keys())
    assert set(STANDARD_SCHEMA.keys()) == all_keys


def test_category_sizes():
    """Verify each category has the expected number of variables."""
    assert len(DEMOGRAPHICS) == 13
    assert len(SOCIOECONOMICS) == 13
    assert len(ECONOMIC_IDENTITY) == 10
    assert len(FINANCIAL_BEHAVIOR) == 10
    assert len(FINANCIAL_SOPHISTICATION) == 8
    assert len(GEOGRAPHY) == 14
    assert len(POLITICAL) == 10
    assert len(POLICY_POSITIONS) == 15
    assert len(PSYCHOLOGY) == 10
    assert len(RELIGION) == 5
    assert len(MEDIA_DIET) == 13
    assert len(SCIENCE_HEALTH) == 11
    assert len(ORIGIN_MOBILITY) == 5
    assert len(SYSTEM_METADATA) == 6


def test_religion_variables_are_prefixed():
    """Religion variables should use religion_ prefix."""
    for key in RELIGION:
        assert key.startswith("religion_"), f"Religion variable '{key}' missing prefix"


def test_validate_range_violation():
    """Out-of-range numeric values should produce errors."""
    profile = {"age": 150, "abortion": 2.5}
    errors = validate_profile(profile, partial=True)
    assert len(errors) == 2


def test_validate_bool_field():
    """Boolean fields should reject non-bool values."""
    profile = {"veteran_status": "yes"}
    errors = validate_profile(profile, partial=True)
    assert len(errors) == 1


def test_validate_float_accepts_int():
    """Float fields should accept int values (e.g., 0 or 1)."""
    profile = {"abortion": 1, "gun_control": 0}
    errors = validate_profile(profile, partial=True)
    assert errors == []


def test_validate_unknown_fields_pass_through():
    """Fields not in schema should not produce errors."""
    profile = {"custom_field": "anything", "age": 30}
    errors = validate_profile(profile, partial=True)
    assert errors == []
