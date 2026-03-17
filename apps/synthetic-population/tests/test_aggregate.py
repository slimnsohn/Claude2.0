import pytest
from engine.aggregate import PollAggregator


@pytest.fixture
def weights():
    return {"A-001": 0.3, "A-002": 0.2, "A-003": 0.5}


@pytest.fixture
def responses():
    return [
        {"archetype_id": "A-001", "response": "yes", "confidence": 8,
         "demographics": {"party_id": "strong_dem", "education": "graduate"}},
        {"archetype_id": "A-002", "response": "no", "confidence": 9,
         "demographics": {"party_id": "strong_rep", "education": "hs_diploma"}},
        {"archetype_id": "A-003", "response": "yes", "confidence": 6,
         "demographics": {"party_id": "lean_dem", "education": "bachelors"}},
    ]


def test_weighted_distribution(weights, responses):
    agg = PollAggregator(weights)
    result = agg.aggregate(responses)
    # yes: A-001(0.3) + A-003(0.5) = 0.8, no: A-002(0.2) = 0.2
    assert result["distribution"]["yes"] == pytest.approx(0.8)
    assert result["distribution"]["no"] == pytest.approx(0.2)


def test_mean_confidence(weights, responses):
    agg = PollAggregator(weights)
    result = agg.aggregate(responses)
    assert result["mean_confidence"] == pytest.approx((8 + 9 + 6) / 3)


def test_demographic_breakdowns(weights, responses):
    agg = PollAggregator(weights)
    result = agg.aggregate(responses)
    assert "party_id" in result["breakdowns"]
    assert "strong_dem" in result["breakdowns"]["party_id"]


def test_handles_missing_archetypes(weights):
    agg = PollAggregator(weights)
    partial = [{"archetype_id": "A-001", "response": "yes", "confidence": 7, "demographics": {}}]
    result = agg.aggregate(partial)
    assert result["n_missing"] == 2  # A-002 and A-003 didn't respond
    assert result["n_responses"] == 1


def test_empty_responses(weights):
    agg = PollAggregator(weights)
    result = agg.aggregate([])
    assert result["n_responses"] == 0
    assert result["n_missing"] == 3


def test_confidence_intervals_present(weights, responses):
    agg = PollAggregator(weights)
    result = agg.aggregate(responses)
    assert "yes" in result["confidence_interval"]
