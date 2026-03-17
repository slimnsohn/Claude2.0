"""BRFSS (CDC Behavioral Risk Factor Surveillance System) source plugin.

Provides health behavior variables with more detail than ACS:
standard variables (health_insurance, disability) plus custom namespaced
variables for chronic conditions, exercise, tobacco, alcohol, and mental health.
"""

from pathlib import Path

import pandas as pd

from pipeline.sources.base import DataSource


# ---------------------------------------------------------------------------
# Value maps
# ---------------------------------------------------------------------------

HEALTH_INSURANCE_MAP = {
    1: True,
    2: False,
    7: None,  # don't know
    9: None,  # refused
}

DISABILITY_MAP = {
    1: True,
    2: False,
    7: None,
    9: None,
}

# BRFSS uses 1/2 for yes/no on chronic conditions
_YES_NO_MAP = {
    1: True,
    2: False,
    7: None,
    9: None,
}

# EXERANY2: any physical activity in past 30 days
# 1=yes, 2=no
EXERCISE_FREQUENCY_MAP = {
    1: "active",
    2: "sedentary",
    7: None,
    9: None,
}

# SMOKDAY2: frequency of smoking
TOBACCO_USE_MAP = {
    1: "daily",
    2: "some_days",
    3: "not_at_all",
    7: None,
    9: None,
}

# DRNKANY5: any drinking in past 30 days → simple binary
ALCOHOL_USE_MAP = {
    1: True,
    2: False,
    7: None,
    9: None,
}

# MENTHLTH: number of days mental health not good (0–30)
# Kept as raw integer; no map — passed through as-is in custom_columns


# ---------------------------------------------------------------------------
# Column maps
# ---------------------------------------------------------------------------

_STANDARD_COLUMN_MAP = {
    "health_insurance": "HLTHPLN1",
    "disability": "DIFFWALK",
    # Match keys
    "age_bracket": "age_bracket",
    "sex": "sex",
    "race": "race",
    "education": "education",
    "state": "state",
}

_CUSTOM_COLUMNS = {
    "chronic_conditions": "CHCCOPD2",    # COPD/chronic condition flag
    "exercise_frequency": "EXERANY2",
    "tobacco_use": "SMOKDAY2",
    "alcohol_use": "DRNKANY5",
    "mental_health_days": "MENTHLTH",
}


class BRFSSSource(DataSource):
    """CDC Behavioral Risk Factor Surveillance System data source plugin."""

    name = "brfss"

    variables_provided = [
        "health_insurance",
        "disability",
    ]

    match_keys = [
        "age_bracket",
        "sex",
        "race",
        "education",
        "state",
    ]

    update_cycle = "annual"

    standard_column_map = _STANDARD_COLUMN_MAP

    variable_maps = {
        "health_insurance": HEALTH_INSURANCE_MAP,
        "disability": DISABILITY_MAP,
    }

    custom_columns = _CUSTOM_COLUMNS

    # Custom maps used in harmonize override for custom columns
    _custom_variable_maps = {
        "chronic_conditions": _YES_NO_MAP,
        "exercise_frequency": EXERCISE_FREQUENCY_MAP,
        "tobacco_use": TOBACCO_USE_MAP,
        "alcohol_use": ALCOHOL_USE_MAP,
        # mental_health_days: numeric, no map
    }

    # ------------------------------------------------------------------
    # harmonize override — apply maps to custom columns too
    # ------------------------------------------------------------------

    def harmonize(self, df: pd.DataFrame) -> pd.DataFrame:
        """Map BRFSS columns to standard schema with custom column mapping."""
        result = pd.DataFrame(index=df.index)

        # Standard columns
        for standard_name, source_col in self.standard_column_map.items():
            if source_col not in df.columns:
                continue
            mapping = self.variable_maps.get(standard_name)
            if mapping:
                result[standard_name] = df[source_col].map(mapping)
            else:
                result[standard_name] = df[source_col]

        # Custom columns — apply specific maps where defined
        for custom_name, source_col in self.custom_columns.items():
            if source_col not in df.columns:
                continue
            mapping = self._custom_variable_maps.get(custom_name)
            if mapping:
                result[f"{self.name}:{custom_name}"] = df[source_col].map(mapping)
            else:
                result[f"{self.name}:{custom_name}"] = df[source_col]

        return result

    # ------------------------------------------------------------------
    # Abstract method implementations
    # ------------------------------------------------------------------

    def download(self) -> Path:
        """Placeholder: BRFSS data available from CDC.

        https://www.cdc.gov/brfss/annual_data/annual_data.htm
        Place the CSV at data/raw/brfss/ and call clean() with that path.
        """
        raise NotImplementedError(
            "BRFSS data must be downloaded from "
            "https://www.cdc.gov/brfss/annual_data/annual_data.htm. "
            "Place the CSV at data/raw/brfss/ and call clean() with that path."
        )

    def clean(self, raw_path) -> pd.DataFrame:
        """Clean raw BRFSS data.

        Accepts either a file path (str/Path) or a pre-loaded DataFrame.

        Steps:
        1. Load from path or pass through DataFrame.
        2. Drop rows missing all health variables.
        3. Return DataFrame ready for harmonize().
        """
        if isinstance(raw_path, pd.DataFrame):
            df = raw_path.copy()
        else:
            df = pd.read_csv(raw_path)

        health_raw_cols = [
            c for c in ["HLTHPLN1", "DIFFWALK", "EXERANY2", "MENTHLTH"]
            if c in df.columns
        ]
        if health_raw_cols:
            df = df.dropna(subset=health_raw_cols, how="all")

        return df
