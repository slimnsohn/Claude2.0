"""Unit tests for the change-detection core (no DB needed)."""
from ingest.core import content_hash, normalize_rules


def test_cosmetic_churn_ignored():
    a = "Resolves YES if the candidate wins the AP race call by 11:59pm ET."
    b = "resolves yes  if the candidate wins the AP race call by 11:59pm ET.  "
    assert content_hash(a) == content_hash(b)


def test_real_edit_detected():
    a = "Resolves YES if the candidate wins the AP race call by 11:59pm ET."
    c = "Resolves YES if the candidate wins the AP race call by 6:00pm ET."
    assert content_hash(a) != content_hash(c)


def test_normalize_collapses_whitespace():
    assert normalize_rules("  A   B \n C ") == "a b c"
