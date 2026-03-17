"""ANES (American National Election Studies) source plugin.

Provides psychology and values variables: Big Five personality dimensions,
racial resentment, authoritarianism, social trust, and political attitudes.
Designed for fusion with the ACS backbone via shared demographic match keys.
"""

from pathlib import Path

import pandas as pd

from pipeline.sources.base import DataSource


# ---------------------------------------------------------------------------
# Value maps — all ANES scales normalized to float 0.0–1.0
# ---------------------------------------------------------------------------

# ANES uses 1-5 scale for most attitude items; map to 0.0–1.0
_SCALE_5PT_MAP = {
    1: 0.0,
    2: 0.25,
    3: 0.5,
    4: 0.75,
    5: 1.0,
}

# Racial resentment: 4-item scale, higher = more resentment
# Coded 1=agree strongly → 1.0 resentment, 5=disagree strongly → 0.0
_RESENTMENT_MAP = {
    1: 1.0,
    2: 0.75,
    3: 0.5,
    4: 0.25,
    5: 0.0,
}

# Authoritarianism: child-rearing values 4-item battery, coded as proportion
# of authoritarian responses (0.0 = none authoritarian, 1.0 = all authoritarian)
# ANES provides pre-computed scale score 0–4; normalize to 0.0–1.0
_AUTH_MAP = {
    0: 0.0,
    1: 0.25,
    2: 0.5,
    3: 0.75,
    4: 1.0,
}

# Social trust: "Generally speaking, most people can be trusted"
# 1=can be trusted, 2=can't be too careful, 3=depends
_SOCIAL_TRUST_MAP = {
    1: 1.0,
    2: 0.0,
    3: 0.5,
}

# Institutional confidence: 1=a great deal … 3=hardly any
_CONFIDENCE_MAP = {
    1: 1.0,
    2: 0.5,
    3: 0.0,
}

# Meritocracy belief: agreement scale 1=agree strongly, 5=disagree strongly
# "America is a fair society where hard work is rewarded"
_MERITOCRACY_MAP = {
    1: 1.0,
    2: 0.75,
    3: 0.5,
    4: 0.25,
    5: 0.0,
}

# Political efficacy: internal efficacy scale, normalized
# 1=agree strongly (high efficacy) → 1.0
_EFFICACY_MAP = {
    1: 1.0,
    2: 0.75,
    3: 0.5,
    4: 0.25,
    5: 0.0,
}


# ---------------------------------------------------------------------------
# Column maps
# ---------------------------------------------------------------------------

_STANDARD_COLUMN_MAP = {
    # Psychology/values variables → ANES column names
    "racial_resentment": "V201600",        # Racial resentment scale (pre-computed)
    "authoritarianism": "V201626",         # Child-rearing authoritarian score
    "social_trust": "V201233",             # People can be trusted
    "openness": "V162333",                 # Big Five: openness
    "conscientiousness": "V162334",        # Big Five: conscientiousness
    "extraversion": "V162335",             # Big Five: extraversion
    "agreeableness": "V162336",            # Big Five: agreeableness
    "neuroticism": "V162337",              # Big Five: neuroticism
    "institutional_confidence": "V201228", # Confidence in institutions
    "meritocracy_belief": "V201401",       # Belief in meritocracy
    "political_efficacy": "V201379",       # Political efficacy (internal)
    # Match keys — already standardized after clean()
    "age_bracket": "age_bracket",
    "sex": "sex",
    "race": "race",
    "education": "education",
    "party_id": "party_id",
}


class ANESSource(DataSource):
    """American National Election Studies data source plugin."""

    name = "anes"

    variables_provided = [
        "racial_resentment",
        "authoritarianism",
        "social_trust",
        "openness",
        "conscientiousness",
        "extraversion",
        "agreeableness",
        "neuroticism",
        "institutional_confidence",
        "meritocracy_belief",
        "political_efficacy",
    ]

    match_keys = [
        "age_bracket",
        "sex",
        "race",
        "education",
        "party_id",
    ]

    update_cycle = "election_year"

    standard_column_map = _STANDARD_COLUMN_MAP

    variable_maps = {
        "racial_resentment": _RESENTMENT_MAP,
        "authoritarianism": _AUTH_MAP,
        "social_trust": _SOCIAL_TRUST_MAP,
        "openness": _SCALE_5PT_MAP,
        "conscientiousness": _SCALE_5PT_MAP,
        "extraversion": _SCALE_5PT_MAP,
        "agreeableness": _SCALE_5PT_MAP,
        "neuroticism": _SCALE_5PT_MAP,
        "institutional_confidence": _CONFIDENCE_MAP,
        "meritocracy_belief": _MERITOCRACY_MAP,
        "political_efficacy": _EFFICACY_MAP,
    }

    custom_columns: dict = {}

    # ------------------------------------------------------------------
    # harmonize override — skip absent optional columns
    # ------------------------------------------------------------------

    def harmonize(self, df: pd.DataFrame) -> pd.DataFrame:
        """Map ANES columns to standard schema, skipping absent columns."""
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
        """Placeholder: ANES data must be obtained from electionstudies.org.

        Returns the expected raw data directory. Actual download requires
        registration at https://electionstudies.org/data-center/.
        Place the CSV at data/raw/anes/ and call clean() with that path.
        """
        raise NotImplementedError(
            "ANES data must be downloaded manually from "
            "https://electionstudies.org/data-center/. "
            "Place the CSV at data/raw/anes/ and call clean() with that path."
        )

    def clean(self, raw_path) -> pd.DataFrame:
        """Clean raw ANES data.

        Accepts either a file path (str/Path) or a pre-loaded DataFrame.

        Steps:
        1. Load from path or pass through DataFrame.
        2. Drop rows missing all psychology variables.
        3. Return DataFrame ready for harmonize().
        """
        if isinstance(raw_path, pd.DataFrame):
            df = raw_path.copy()
        else:
            df = pd.read_csv(raw_path)

        # Drop rows with no psychology signal at all
        psych_raw_cols = [
            c for c in ["V201600", "V201626", "V201233", "V162333"]
            if c in df.columns
        ]
        if psych_raw_cols:
            df = df.dropna(subset=psych_raw_cols, how="all")

        return df
