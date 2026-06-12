import pytest
from pathlib import Path
from engine.opinion import OpinionEngine


@pytest.fixture
def engine():
    ces_path = Path("data/raw/ces/ces_2024_common.csv")
    if not ces_path.exists():
        pytest.skip("CES data not available")
    return OpinionEngine(str(ces_path))


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
