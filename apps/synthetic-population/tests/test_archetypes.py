import pytest
import pandas as pd
from generator.archetypes import ArchetypeBuilder


@pytest.fixture
def profiles():
    """30 profiles with clustering variables."""
    data = []
    for _ in range(10):
        data.append({"party_id": "strong_dem", "race": "black", "education": "graduate",
                      "religion_attendance": "never", "urban_rural": "urban", "info_ecosystem": "mainstream"})
        data.append({"party_id": "strong_rep", "race": "white", "education": "hs_diploma",
                      "religion_attendance": "weekly", "urban_rural": "rural", "info_ecosystem": "right_alternative"})
        data.append({"party_id": "independent", "race": "hispanic", "education": "some_college",
                      "religion_attendance": "monthly", "urban_rural": "suburban", "info_ecosystem": "mainstream"})
    return pd.DataFrame(data)


def test_build_assigns_archetype_ids(profiles):
    builder = ArchetypeBuilder(min_cell_size=3)
    result = builder.build(profiles)
    assert "archetype_id" in result.columns
    assert result["archetype_id"].notna().all()


def test_weights_sum_to_one(profiles):
    builder = ArchetypeBuilder(min_cell_size=3)
    builder.build(profiles)
    weights = builder.get_weights()
    assert abs(sum(weights.values()) - 1.0) < 0.01


def test_archetype_count_reasonable(profiles):
    builder = ArchetypeBuilder(min_cell_size=3)
    builder.build(profiles)
    # Should have ~3 archetypes for 3 distinct groups
    assert 1 <= len(builder.archetypes) <= 10


def test_get_representative(profiles):
    builder = ArchetypeBuilder(min_cell_size=3)
    result = builder.build(profiles)
    arch_id = result["archetype_id"].iloc[0]
    rep = builder.get_representative(result, arch_id)
    assert isinstance(rep, dict)
    assert "party_id" in rep


def test_small_cells_collapsed(profiles):
    # Add one unique profile that will be in a small cell
    extra = pd.DataFrame([{"party_id": "lean_dem", "race": "asian", "education": "bachelors",
                           "religion_attendance": "yearly", "urban_rural": "urban", "info_ecosystem": "left_alternative"}])
    big_profiles = pd.concat([profiles, extra], ignore_index=True)
    builder = ArchetypeBuilder(min_cell_size=3)
    result = builder.build(big_profiles)
    # The lone asian profile should be merged into another archetype
    assert result["archetype_id"].notna().all()
