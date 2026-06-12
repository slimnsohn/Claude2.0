import pytest
import pandas as pd
from pathlib import Path
from engine.opinion import OpinionEngine


@pytest.fixture
def engine():
    ces_path = Path("data/raw/ces/ces_2024_common.csv")
    if not ces_path.exists():
        pytest.skip("CES data not available")
    return OpinionEngine(str(ces_path))


@pytest.fixture
def engine_fixture(tmp_path):
    """OpinionEngine backed by a tiny synthetic CES fixture — no real data needed.

    100 rows, all demographic values identical (independent/bachelors/35-44/white/suburban)
    so every profile gets the same 100 neighbours and the distribution is deterministic.

    CC24_301  (economy retro, BELIEF_SIGN=+1): 40 yes(1), 40 no(5), 20 unsure(3)
              → baseline yes_p ≈ 0.40, firmly interior
    CC24_308a_4 (Ukraine arms, BELIEF_SIGN=0):  50 selected(1), 50 not(2)
    """
    import numpy as np

    n = 100

    # Raw demographic columns that CESLoader.get_data() harmonises
    pid7 = [4] * n           # 4 → independent
    educ = [5] * n           # 5 → bachelors
    birthyr = [1984] * n     # 2026-1984=42 → age_bracket 35-44
    gender4 = [1] * n        # 1 → M
    race = [1] * n           # 1 → white
    urbancity = [2] * n      # 2 → suburban

    # CC24_301: 40 rows=1 (yes), 40 rows=5 (no), 20 rows=3 (unsure)
    cc301 = [1] * 40 + [5] * 40 + [3] * 20

    # CC24_308a_4: 50 selected(1), 50 not selected(2)
    cc308a4 = [1] * 50 + [2] * 50

    df = pd.DataFrame({
        "pid7": pid7, "educ": educ, "birthyr": birthyr,
        "gender4": gender4, "race": race, "urbancity": urbancity,
        "CC24_301": cc301, "CC24_308a_4": cc308a4,
    })

    csv_path = tmp_path / "fixture_ces.csv"
    df.to_csv(csv_path, index=False)
    return OpinionEngine(str(csv_path), k=100)


class TestOpinionEngine:
    def test_returns_opinion_tuple(self, engine):
        profile = {
            "party_id": "strong_dem", "education": "bachelors",
            "age_bracket": "35-44", "race": "white", "urban_rural": "urban",
        }
        opinion, confidence, reasoning = engine.get_opinion(
            "Do you approve of Trump's job performance?", profile
        )
        assert opinion in ("yes", "no", "unsure")
        assert 1 <= confidence <= 10
        assert isinstance(reasoning, str)
        assert len(reasoning) > 0

    def test_strong_dem_disapproves_trump(self, engine):
        profile = {
            "party_id": "strong_dem", "education": "graduate",
            "age_bracket": "45-54", "race": "white", "urban_rural": "urban",
        }
        opinions = [
            engine.get_opinion("Do you approve of Trump's job performance?", profile)[0]
            for _ in range(50)
        ]
        no_count = opinions.count("no")
        assert no_count > 30, f"Expected >30 'no' from strong dem, got {no_count}"

    def test_strong_rep_approves_trump(self, engine):
        profile = {
            "party_id": "strong_rep", "education": "hs_diploma",
            "age_bracket": "55-64", "race": "white", "urban_rural": "rural",
        }
        opinions = [
            engine.get_opinion("Do you approve of Trump's job performance?", profile)[0]
            for _ in range(50)
        ]
        yes_count = opinions.count("yes")
        assert yes_count > 30, f"Expected >30 'yes' from strong rep, got {yes_count}"

    def test_unmatched_question_returns_none(self, engine):
        profile = {"party_id": "dem", "education": "bachelors",
                   "age_bracket": "25-34", "race": "white", "urban_rural": "urban"}
        result = engine.get_opinion("Do you like pizza?", profile)
        assert result is None

    def test_distribution_method(self, engine):
        profile = {
            "party_id": "independent", "education": "some_college",
            "age_bracket": "35-44", "race": "black", "urban_rural": "suburban",
        }
        dist = engine.get_distribution(
            "Do you approve of Trump's job performance?", profile
        )
        assert dist is not None
        assert "yes" in dist and "no" in dist and "unsure" in dist
        total = dist["yes"] + dist["no"] + dist["unsure"]
        assert abs(total - 1.0) < 0.01
        assert all(0 <= dist[k] <= 1 for k in ["yes", "no", "unsure"])

    def test_neighbor_count(self, engine):
        profile = {
            "party_id": "dem", "education": "bachelors",
            "age_bracket": "25-34", "race": "white", "urban_rural": "urban",
        }
        dist = engine.get_distribution(
            "Is the economy getting better or worse?", profile,
        )
        assert dist is not None
        assert dist.get("_n_neighbors", 0) >= 10


def test_belief_shift_applied_per_persona(engine_fixture):
    """Personas with opposite economy beliefs diverge in their distributions."""
    base_profile = {"party_id": "independent", "education": "bachelors",
                    "age_bracket": "35-44", "race": "white", "urban_rural": "suburban"}
    up = {**base_profile, "beliefs": {"economy": {"shift": 0.10, "exposures": 5,
                                                  "last_updated": "2026-06-11T09:00:00"}}}
    down = {**base_profile, "beliefs": {"economy": {"shift": -0.10, "exposures": 5,
                                                    "last_updated": "2026-06-11T09:00:00"}}}
    q = "Is the economy getting better or worse?"
    d_up = engine_fixture.get_distribution(q, up)
    d_down = engine_fixture.get_distribution(q, down)
    d_base = engine_fixture.get_distribution(q, base_profile)
    assert d_up["yes"] > d_base["yes"] > d_down["yes"]


def test_belief_ignored_when_sign_zero(engine_fixture):
    """Ukraine-arms column has BELIEF_SIGN 0 (ambiguous partisan polarity) —
    beliefs must not move it."""
    base = {"party_id": "independent", "education": "bachelors",
            "age_bracket": "35-44", "race": "white", "urban_rural": "suburban"}
    bel = {**base, "beliefs": {"foreign_policy": {"shift": 0.15, "exposures": 9,
                                                  "last_updated": "2026-06-11T09:00:00"}}}
    q = "Do you support providing arms to Ukraine?"
    assert engine_fixture.get_distribution(q, bel)["yes"] == \
           engine_fixture.get_distribution(q, base)["yes"]


def test_party_shift_fallback_without_beliefs(engine_fixture):
    """Profiles lacking beliefs still respond to legacy world_shifts."""
    base = {"party_id": "rep", "education": "bachelors", "age_bracket": "35-44",
            "race": "white", "urban_rural": "suburban"}
    q = "Is the economy getting better or worse?"
    d_plain = engine_fixture.get_distribution(q, base)
    d_shift = engine_fixture.get_distribution(q, base, world_shifts={"rep": 0.05})
    assert d_shift["yes"] > d_plain["yes"]
