"""GSS (General Social Survey) source plugin.

Provides religion and social capital variables: religious affiliation,
denomination, attendance, biblical literalism, importance, social trust,
and institutional confidence.
"""

from pathlib import Path

import pandas as pd

from pipeline.sources.base import DataSource


# ---------------------------------------------------------------------------
# Value maps
# ---------------------------------------------------------------------------

RELIGION_AFFILIATION_MAP = {
    1: "protestant",
    2: "catholic",
    3: "jewish",
    4: "none",
    5: "other",
    6: "buddhist",
    7: "hindu",
    8: "orthodox",
    9: "muslim",
    10: "native_american",
    11: "inter_nondenominational",
}

RELIGION_DENOMINATION_MAP = {
    10: "baptist",
    11: "methodist",
    12: "lutheran",
    13: "presbyterian",
    14: "episcopal",
    20: "evangelical",
    30: "roman_catholic",
    40: "jewish",
    50: "none",
    98: "other",
}

# ATTEND: how often attend religious services
# 0=never, 8=more than once a week → normalize to 0.0–1.0
RELIGION_ATTENDANCE_MAP = {
    0: 0.0,
    1: 0.07,  # less than once a year
    2: 0.14,  # once a year
    3: 0.28,  # several times a year
    4: 0.42,  # once a month
    5: 0.57,  # 2-3 times a month
    6: 0.71,  # nearly every week
    7: 0.85,  # every week
    8: 1.0,   # more than once a week
}

# BIBLE: attitudes toward the Bible
RELIGION_BIBLICAL_LITERALISM_MAP = {
    1: "literal_word",
    2: "inspired_not_literal",
    3: "ancient_book",
    4: "other",
}

# RELITEN: strength of religious identity
RELIGION_IMPORTANCE_MAP = {
    1: 1.0,   # strong
    2: 0.67,  # somewhat strong
    3: 0.33,  # not very strong
    4: 0.0,   # no religion
}

# TRUST: general social trust
SOCIAL_TRUST_MAP = {
    1: 1.0,   # can trust
    2: 0.0,   # can't be too careful
    3: 0.5,   # depends
}

# CONFINAN, CONBUS, etc. — confidence in institutions
# 1=a great deal, 2=only some, 3=hardly any
INSTITUTIONAL_CONFIDENCE_MAP = {
    1: 1.0,
    2: 0.5,
    3: 0.0,
}


# ---------------------------------------------------------------------------
# Column maps
# ---------------------------------------------------------------------------

_STANDARD_COLUMN_MAP = {
    "religion_affiliation": "RELIG",
    "religion_denomination": "DENOM",
    "religion_attendance": "ATTEND",
    "religion_biblical_literalism": "BIBLE",
    "religion_importance": "RELITEN",
    "social_trust": "TRUST",
    "institutional_confidence": "CONFINAN",
    # Match keys
    "age_bracket": "age_bracket",
    "sex": "sex",
    "race": "race",
    "education": "education",
}


class GSSSource(DataSource):
    """General Social Survey data source plugin."""

    name = "gss"

    variables_provided = [
        "religion_affiliation",
        "religion_denomination",
        "religion_attendance",
        "religion_biblical_literalism",
        "religion_importance",
        "social_trust",
        "institutional_confidence",
    ]

    match_keys = [
        "age_bracket",
        "sex",
        "race",
        "education",
    ]

    update_cycle = "biennial"

    standard_column_map = _STANDARD_COLUMN_MAP

    variable_maps = {
        "religion_affiliation": RELIGION_AFFILIATION_MAP,
        "religion_denomination": RELIGION_DENOMINATION_MAP,
        "religion_attendance": RELIGION_ATTENDANCE_MAP,
        "religion_biblical_literalism": RELIGION_BIBLICAL_LITERALISM_MAP,
        "religion_importance": RELIGION_IMPORTANCE_MAP,
        "social_trust": SOCIAL_TRUST_MAP,
        "institutional_confidence": INSTITUTIONAL_CONFIDENCE_MAP,
    }

    custom_columns: dict = {}

    # ------------------------------------------------------------------
    # harmonize override — skip absent optional columns
    # ------------------------------------------------------------------

    def harmonize(self, df: pd.DataFrame) -> pd.DataFrame:
        """Map GSS columns to standard schema, skipping absent columns."""
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
        """Placeholder: GSS data must be obtained from NORC at gss.norc.org.

        Place the CSV at data/raw/gss/ and call clean() with that path.
        """
        raise NotImplementedError(
            "GSS data must be downloaded from https://gss.norc.org/. "
            "Place the CSV at data/raw/gss/ and call clean() with that path."
        )

    def clean(self, raw_path) -> pd.DataFrame:
        """Clean raw GSS data.

        Accepts either a file path (str/Path) or a pre-loaded DataFrame.

        Steps:
        1. Load from path or pass through DataFrame.
        2. Drop rows missing all religion variables.
        3. Return DataFrame ready for harmonize().
        """
        if isinstance(raw_path, pd.DataFrame):
            df = raw_path.copy()
        else:
            df = pd.read_csv(raw_path)

        religion_raw_cols = [
            c for c in ["RELIG", "ATTEND", "TRUST", "BIBLE"]
            if c in df.columns
        ]
        if religion_raw_cols:
            df = df.dropna(subset=religion_raw_cols, how="all")

        return df
