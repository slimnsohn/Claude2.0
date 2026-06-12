# tests/test_news_scoring.py
import json
from unittest.mock import patch, MagicMock

from engine.news_scoring import (
    detect_topics, detect_direction, compute_party_shift,
    score_events_keyword, score_events_llm, score_events, BELIEF_TOPICS,
)

HEADLINES = [
    {"title": "Inflation falls to 2.1% as economy beats expectations", "description": "", "feed": "AP"},
    {"title": "Border crossings surge to record high", "description": "", "feed": "BBC"},
]


def test_detect_topics_keyword():
    assert "economy" in detect_topics("inflation falls as economy improves")
    assert "immigration" in detect_topics("border crossings surge")
    assert detect_topics("local bake sale") == ["general"]


def test_keyword_scoring_shapes():
    events = score_events_keyword(HEADLINES)
    assert len(events) == 2
    e = events[0]
    assert e["scoring_method"] == "keyword"
    assert isinstance(e["direction"], float)
    assert 0.0 <= e["salience"] <= 1.0
    assert set(e["framing"].keys()) == {"right", "left", "mainstream"}
    # Keyword fallback: neutral framing (all families = 1.0)
    assert all(v == 1.0 for v in e["framing"].values())
    assert "economy" in e["topics"]


def _fake_llm_response(payload):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"content": [{"type": "text", "text": json.dumps(payload)}]}
    return resp


def test_llm_scoring_parses_and_clamps():
    payload = [
        {"topics": ["economy"], "direction": 0.8, "salience": 1.7,
         "framing": {"right": 0.4, "left": 1.0, "mainstream": 0.9}},
        {"topics": ["immigration", "bogus_topic"], "direction": -0.6, "salience": 0.9,
         "framing": {"right": 1.0, "left": -0.5, "mainstream": 0.7}},
    ]
    with patch("engine.news_scoring.requests.post", return_value=_fake_llm_response(payload)):
        events = score_events_llm(HEADLINES, api_key="test-key")
    assert events is not None and len(events) == 2
    assert events[0]["salience"] == 1.0          # clamped
    assert events[1]["topics"] == ["immigration"]  # unknown topic dropped
    assert events[0]["scoring_method"] == "llm"


def test_llm_scoring_malformed_returns_none():
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"content": [{"type": "text", "text": "not json"}]}
    with patch("engine.news_scoring.requests.post", return_value=resp):
        assert score_events_llm(HEADLINES, api_key="k") is None


def test_score_events_falls_back_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    events, method = score_events(HEADLINES)
    assert method == "keyword"
    assert len(events) == 2


def test_party_shift_unchanged_behavior():
    shifts = compute_party_shift(["economy"], "positive")
    assert shifts["rep"] > 0 and shifts["dem"] < 0  # incumbent = rep
