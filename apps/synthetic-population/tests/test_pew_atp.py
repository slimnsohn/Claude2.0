"""Tests for the Pew ATP (American Trends Panel) source plugin."""

import pytest
import pandas as pd

from pipeline.sources.pew_atp import (
    PewATPSource,
    PRIMARY_NEWS_SOURCE_MAP,
    SOCIAL_MEDIA_PRIMARY_MAP,
    MEDIA_TRUST_MAP,
    INFO_ECOSYSTEM_MAP,
    VACCINE_ATTITUDE_MAP,
    CLIMATE_CHANGE_BELIEF_MAP,
    TRUST_SCIENTIFIC_ESTABLISHMENT_MAP,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def source():
    return PewATPSource()


@pytest.fixture
def raw_pew_data():
    """Minimal Pew ATP-shaped DataFrame covering key columns."""
    return pd.DataFrame({
        "NEWSSORC1": [1, 2, 5],       # tv, online, social media
        "NEWSSORC2": [2, 5, 1],       # online, social media, tv
        "SMSITEPRIM": [1, 5, 3],      # facebook, tiktok, twitter_x
        "SMNEWS": [1, 3, 5],          # facebook, twitter_x, tiktok
        "PODCAST": [1, 2, 1],         # yes, no, yes
        "MEDIRUST": [4, 2, 1],        # a lot, not much, not at all
        "INFOECOS": [1, 3, 4],        # mainstream, partisan_left, partisan_right
        "VAXXATT": [1, 3, 5],         # strongly_pro, somewhat_hesitant, anti
        "CLIMBELIEF": [1, 2, 3],      # human_caused, natural_patterns, no_solid_evidence
        "SCITRUST": [1, 2, 4],        # a great deal, some, not at all
        "age_bracket": ["18-24", "35-44", "65+"],
        "sex": ["F", "M", "F"],
        "race": ["white", "black", "hispanic"],
        "education": ["bachelors", "hs_diploma", "graduate"],
        "party_id": ["dem", "independent", "rep"],
    })


# ---------------------------------------------------------------------------
# Metadata tests
# ---------------------------------------------------------------------------

def test_source_name(source):
    assert source.name == "pew_atp"


def test_update_cycle(source):
    assert source.update_cycle == "annual"


def test_variables_provided(source):
    expected = [
        "primary_news_source", "secondary_news_source",
        "social_media_primary", "social_media_news",
        "podcast_listener", "media_trust", "info_ecosystem",
        "vaccine_attitude", "climate_change_belief",
        "trust_scientific_establishment",
    ]
    for var in expected:
        assert var in source.variables_provided, f"Missing variable: {var}"


def test_variables_provided_count(source):
    assert len(source.variables_provided) == 10


# ---------------------------------------------------------------------------
# Match keys
# ---------------------------------------------------------------------------

def test_match_keys(source):
    for key in ["age_bracket", "sex", "race", "education", "party_id"]:
        assert key in source.match_keys


def test_match_keys_count(source):
    assert len(source.match_keys) == 5


# ---------------------------------------------------------------------------
# Variable mapping tests
# ---------------------------------------------------------------------------

def test_primary_news_source_mapping(source, raw_pew_data):
    cleaned = source.clean(raw_pew_data)
    result = source.harmonize(cleaned)
    assert list(result["primary_news_source"]) == ["television", "online_news", "social_media"]


def test_media_trust_mapping(source, raw_pew_data):
    cleaned = source.clean(raw_pew_data)
    result = source.harmonize(cleaned)
    # MEDIRUST: [4, 2, 1] → [1.0, 0.33, 0.0]
    assert list(result["media_trust"]) == [1.0, 0.33, 0.0]


def test_vaccine_attitude_mapping(source, raw_pew_data):
    cleaned = source.clean(raw_pew_data)
    result = source.harmonize(cleaned)
    assert list(result["vaccine_attitude"]) == ["strongly_pro", "somewhat_hesitant", "anti"]


def test_climate_change_belief_mapping(source, raw_pew_data):
    cleaned = source.clean(raw_pew_data)
    result = source.harmonize(cleaned)
    assert list(result["climate_change_belief"]) == [
        "human_caused", "natural_patterns", "no_solid_evidence"
    ]


def test_trust_scientific_establishment_mapping(source, raw_pew_data):
    cleaned = source.clean(raw_pew_data)
    result = source.harmonize(cleaned)
    # SCITRUST: [1, 2, 4] → [1.0, 0.67, 0.0]
    assert list(result["trust_scientific_establishment"]) == [1.0, 0.67, 0.0]


def test_podcast_listener_binary_mapping(source, raw_pew_data):
    cleaned = source.clean(raw_pew_data)
    result = source.harmonize(cleaned)
    # PODCAST: [1, 2, 1] → [True, False, True]
    assert list(result["podcast_listener"]) == [True, False, True]


# ---------------------------------------------------------------------------
# clean() behavior
# ---------------------------------------------------------------------------

def test_clean_accepts_dataframe(source, raw_pew_data):
    result = source.clean(raw_pew_data)
    assert isinstance(result, pd.DataFrame)
    assert "NEWSSORC1" in result.columns


def test_clean_does_not_mutate_input(source, raw_pew_data):
    original_cols = list(raw_pew_data.columns)
    source.clean(raw_pew_data)
    assert list(raw_pew_data.columns) == original_cols


# ---------------------------------------------------------------------------
# harmonize() behavior
# ---------------------------------------------------------------------------

def test_harmonize_renames_raw_columns(source, raw_pew_data):
    cleaned = source.clean(raw_pew_data)
    result = source.harmonize(cleaned)
    assert "primary_news_source" in result.columns
    assert "NEWSSORC1" not in result.columns


def test_match_keys_preserved_after_harmonize(source, raw_pew_data):
    cleaned = source.clean(raw_pew_data)
    result = source.harmonize(cleaned)
    assert list(result["party_id"]) == ["dem", "independent", "rep"]


# ---------------------------------------------------------------------------
# download() raises NotImplementedError
# ---------------------------------------------------------------------------

def test_download_raises(source):
    with pytest.raises(NotImplementedError):
        source.download()


# ---------------------------------------------------------------------------
# match_config()
# ---------------------------------------------------------------------------

def test_match_config_structure(source):
    cfg = source.match_config()
    assert cfg["source"] == "pew_atp"
    assert cfg["match_keys"] == source.match_keys
    assert cfg["variables"] == source.variables_provided
