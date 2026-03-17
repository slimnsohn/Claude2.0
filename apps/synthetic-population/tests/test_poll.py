import pytest
from engine.poll import PollRunner


@pytest.fixture
def registry():
    return [
        {"archetype_id": "A-001", "backstory": "I am a 34-year-old white man from rural Michigan.",
         "party_id": "lean_rep", "race": "white", "education": "some_college",
         "urban_rural": "rural", "primary_news_source": "fox_news", "drift_log": []},
        {"archetype_id": "A-002", "backstory": "I am a 52-year-old black woman from urban Georgia.",
         "party_id": "strong_dem", "race": "black", "education": "graduate",
         "urban_rural": "urban", "primary_news_source": "msnbc", "drift_log": []},
        {"archetype_id": "A-003", "backstory": "I am a 28-year-old Hispanic man from suburban Texas.",
         "party_id": "independent", "race": "hispanic", "education": "bachelors",
         "urban_rural": "suburban", "primary_news_source": "cnn", "drift_log": []},
    ]


@pytest.fixture
def weights():
    return {"A-001": 0.4, "A-002": 0.35, "A-003": 0.25}


@pytest.fixture
def runner(tmp_path):
    return PollRunner(polls_dir=str(tmp_path / "polls"))


def test_prepare_generates_prompts(runner, registry, weights):
    poll_id = runner.prepare("Should the US ban TikTok?", registry, weights)
    assert poll_id.startswith("POLL-")
    assert len(runner.prompts) == 3


def test_prepare_saves_prompts_file(runner, registry, weights, tmp_path):
    poll_id = runner.prepare("Test question?", registry, weights)
    prompts_file = tmp_path / "polls" / poll_id / "prompts.txt"
    assert prompts_file.exists()
    content = prompts_file.read_text()
    assert "ARCHETYPE A-001" in content


def test_record_response_checks_hedge(runner, registry, weights):
    runner.prepare("Test?", registry, weights)
    result = runner.record_response("A-001", "Absolutely not!", opinion="no", confidence=9)
    assert result["hedge_score"] < 0.3
    assert result["archetype_id"] == "A-001"


def test_aggregate_produces_results(runner, registry, weights):
    runner.prepare("Test?", registry, weights)
    runner.record_response("A-001", "Yes!", opinion="yes", confidence=8)
    runner.record_response("A-002", "Yes!", opinion="yes", confidence=7)
    runner.record_response("A-003", "No way!", opinion="no", confidence=9)
    result = runner.aggregate()
    assert "distribution" in result
    assert result["n_responses"] == 3


def test_aggregate_saves_results(runner, registry, weights, tmp_path):
    poll_id = runner.prepare("Test?", registry, weights)
    runner.record_response("A-001", "Yes!", opinion="yes", confidence=8)
    runner.aggregate()
    results_file = tmp_path / "polls" / poll_id / "results.json"
    assert results_file.exists()


def test_partial_responses(runner, registry, weights):
    runner.prepare("Test?", registry, weights)
    runner.record_response("A-001", "Yes!", opinion="yes", confidence=8)
    result = runner.aggregate()
    assert result["n_missing"] == 2
