from engine.prompts import build_poll_prompt


def test_prompt_includes_backstory():
    profile = {"backstory": "I am a 34-year-old white man from rural Michigan."}
    prompt = build_poll_prompt(profile, "Should the US ban TikTok?")
    assert "34-year-old white man" in prompt


def test_prompt_includes_conviction_anchoring():
    profile = {"backstory": "I am a nurse from Ohio."}
    prompt = build_poll_prompt(profile, "Any question?")
    assert "NOT a policy analyst" in prompt or "real opinions" in prompt


def test_prompt_includes_media_diet():
    profile = {
        "backstory": "I am a nurse.",
        "primary_news_source": "fox_news",
        "social_media_primary": "facebook",
    }
    prompt = build_poll_prompt(profile, "Any question?")
    assert "Fox News" in prompt or "fox" in prompt.lower()


def test_prompt_includes_prior_opinions():
    profile = {
        "backstory": "I am a nurse.",
        "drift_log": [
            {"topic": "immigration", "position": "oppose", "confidence": 8},
        ],
    }
    prompt = build_poll_prompt(profile, "Should we increase immigration?")
    assert "immigration" in prompt.lower()


def test_prompt_requests_structured_response():
    profile = {"backstory": "I am a person."}
    prompt = build_poll_prompt(profile, "Any question?")
    assert "yes/no/unsure" in prompt.lower() or "confidence" in prompt.lower()
