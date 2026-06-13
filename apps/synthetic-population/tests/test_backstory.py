from generator.backstory import generate_backstory


def test_backstory_contains_key_demographics():
    profile = {
        "age": 34, "sex": "M", "race": "white", "education": "some_college",
        "state": "MI", "urban_rural": "rural", "occupation": "diesel_mechanic",
        "income": 52000, "marital_status": "married", "children_count": 3,
        "religion_affiliation": "evangelical", "religion_attendance": "weekly",
        "party_id": "lean_rep", "vote_2024": "trump",
        "primary_news_source": "fox_news", "social_media_primary": "facebook",
        "income_source": "wages", "tax_approach": "software_basic",
    }
    story = generate_backstory(profile)
    assert "34" in story
    assert "Michigan" in story or "MI" in story
    assert "married" in story.lower()


def test_backstory_varies_across_calls():
    profile = {
        "age": 52, "sex": "F", "race": "black", "education": "graduate",
        "state": "GA", "urban_rural": "urban", "occupation": "attorney",
        "income": 120000, "marital_status": "divorced", "children_count": 1,
        "religion_affiliation": "none", "religion_attendance": "never",
        "party_id": "strong_dem", "vote_2024": "harris",
        "primary_news_source": "msnbc", "social_media_primary": "twitter",
        "income_source": "wages", "tax_approach": "professional_cpa",
    }
    stories = {generate_backstory(profile) for _ in range(10)}
    assert len(stories) > 1


def test_backstory_includes_financial_identity():
    profile = {
        "age": 45, "sex": "M", "race": "white", "education": "hs_diploma",
        "state": "TX", "urban_rural": "rural", "occupation": "contractor",
        "income": 95000, "marital_status": "married", "children_count": 2,
        "religion_affiliation": "evangelical", "religion_attendance": "weekly",
        "party_id": "strong_rep", "vote_2024": "trump",
        "primary_news_source": "fox_news", "social_media_primary": "facebook",
        "income_source": "self_employment", "tax_approach": "professional_cpa",
        "business_size": "1-10_employees",
    }
    story = generate_backstory(profile)
    assert any(term in story.lower() for term in ["own", "business", "self-employed", "run"])
