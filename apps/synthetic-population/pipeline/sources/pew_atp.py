"""Pew ATP (American Trends Panel) source plugin.

Provides media consumption and attitudes variables: news sources, social media
usage, media trust, and selected science/health attitudes.
"""

from pathlib import Path

import pandas as pd

from pipeline.sources.base import DataSource


# ---------------------------------------------------------------------------
# Value maps
# ---------------------------------------------------------------------------

PRIMARY_NEWS_SOURCE_MAP = {
    1: "television",
    2: "online_news",
    3: "radio",
    4: "print_newspaper",
    5: "social_media",
    6: "podcasts",
    7: "word_of_mouth",
    8: "other",
}

SECONDARY_NEWS_SOURCE_MAP = PRIMARY_NEWS_SOURCE_MAP  # same codes

SOCIAL_MEDIA_PRIMARY_MAP = {
    1: "facebook",
    2: "youtube",
    3: "twitter_x",
    4: "instagram",
    5: "tiktok",
    6: "reddit",
    7: "linkedin",
    8: "none",
    9: "other",
}

SOCIAL_MEDIA_NEWS_MAP = SOCIAL_MEDIA_PRIMARY_MAP  # same platform codes

# YES/NO binary
_BINARY_MAP = {
    1: True,
    2: False,
}

# Media trust: 1–4 scale, 1=not at all → 0.0, 4=a lot → 1.0
MEDIA_TRUST_MAP = {
    1: 0.0,
    2: 0.33,
    3: 0.67,
    4: 1.0,
}

INFO_ECOSYSTEM_MAP = {
    1: "mainstream",
    2: "alternative",
    3: "partisan_left",
    4: "partisan_right",
    5: "mixed",
}

VACCINE_ATTITUDE_MAP = {
    1: "strongly_pro",
    2: "somewhat_pro",
    3: "somewhat_hesitant",
    4: "strongly_hesitant",
    5: "anti",
}

CLIMATE_CHANGE_BELIEF_MAP = {
    1: "human_caused",
    2: "natural_patterns",
    3: "no_solid_evidence",
    4: "not_happening",
}

# Trust in scientific establishment: 1=a great deal … 4=not at all
TRUST_SCIENTIFIC_ESTABLISHMENT_MAP = {
    1: 1.0,
    2: 0.67,
    3: 0.33,
    4: 0.0,
}


# ---------------------------------------------------------------------------
# Column maps
# ---------------------------------------------------------------------------

_STANDARD_COLUMN_MAP = {
    "primary_news_source": "NEWSSORC1",
    "secondary_news_source": "NEWSSORC2",
    "social_media_primary": "SMSITEPRIM",
    "social_media_news": "SMNEWS",
    "podcast_listener": "PODCAST",
    "media_trust": "MEDIRUST",
    "info_ecosystem": "INFOECOS",
    "vaccine_attitude": "VAXXATT",
    "climate_change_belief": "CLIMBELIEF",
    "trust_scientific_establishment": "SCITRUST",
    # Match keys
    "age_bracket": "age_bracket",
    "sex": "sex",
    "race": "race",
    "education": "education",
    "party_id": "party_id",
}


class PewATPSource(DataSource):
    """Pew American Trends Panel data source plugin."""

    name = "pew_atp"

    variables_provided = [
        "primary_news_source",
        "secondary_news_source",
        "social_media_primary",
        "social_media_news",
        "podcast_listener",
        "media_trust",
        "info_ecosystem",
        "vaccine_attitude",
        "climate_change_belief",
        "trust_scientific_establishment",
    ]

    match_keys = [
        "age_bracket",
        "sex",
        "race",
        "education",
        "party_id",
    ]

    update_cycle = "annual"

    standard_column_map = _STANDARD_COLUMN_MAP

    variable_maps = {
        "primary_news_source": PRIMARY_NEWS_SOURCE_MAP,
        "secondary_news_source": SECONDARY_NEWS_SOURCE_MAP,
        "social_media_primary": SOCIAL_MEDIA_PRIMARY_MAP,
        "social_media_news": SOCIAL_MEDIA_NEWS_MAP,
        "podcast_listener": _BINARY_MAP,
        "media_trust": MEDIA_TRUST_MAP,
        "info_ecosystem": INFO_ECOSYSTEM_MAP,
        "vaccine_attitude": VACCINE_ATTITUDE_MAP,
        "climate_change_belief": CLIMATE_CHANGE_BELIEF_MAP,
        "trust_scientific_establishment": TRUST_SCIENTIFIC_ESTABLISHMENT_MAP,
    }

    custom_columns: dict = {}

    # ------------------------------------------------------------------
    # harmonize override — skip absent optional columns
    # ------------------------------------------------------------------

    def harmonize(self, df: pd.DataFrame) -> pd.DataFrame:
        """Map Pew ATP columns to standard schema, skipping absent columns."""
        result = pd.DataFrame(index=df.index)
        for standard_name, source_col in self.standard_column_map.items():
            if source_col not in df.columns:
                continue
            mapping = self.variable_maps.get(standard_name)
            if mapping:
                result[standard_name] = df[source_col].map(mapping)
            else:
                result[standard_name] = df[source_col]
        for custom_name, source_col in self.custom_columns.items():
            if source_col in df.columns:
                result[f"{self.name}:{custom_name}"] = df[source_col]
        return result

    # ------------------------------------------------------------------
    # Abstract method implementations
    # ------------------------------------------------------------------

    def download(self) -> Path:
        """Placeholder: Pew ATP data must be requested from pewresearch.org.

        Place the CSV at data/raw/pew_atp/ and call clean() with that path.
        """
        raise NotImplementedError(
            "Pew ATP data must be requested from https://www.pewresearch.org/american-trends-panel-datasets/. "
            "Place the CSV at data/raw/pew_atp/ and call clean() with that path."
        )

    def clean(self, raw_path) -> pd.DataFrame:
        """Clean raw Pew ATP data.

        Accepts either a file path (str/Path) or a pre-loaded DataFrame.

        Steps:
        1. Load from path or pass through DataFrame.
        2. Drop rows missing all media/attitude variables.
        3. Return DataFrame ready for harmonize().
        """
        if isinstance(raw_path, pd.DataFrame):
            df = raw_path.copy()
        else:
            df = pd.read_csv(raw_path)

        media_raw_cols = [
            c for c in ["NEWSSORC1", "MEDIRUST", "VAXXATT", "CLIMBELIEF"]
            if c in df.columns
        ]
        if media_raw_cols:
            df = df.dropna(subset=media_raw_cols, how="all")

        return df
