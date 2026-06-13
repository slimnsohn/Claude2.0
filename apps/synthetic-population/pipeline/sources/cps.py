"""CPS (Current Population Survey) source plugin.

Provides labor market variables: employment status, occupation, industry,
union membership, hours worked, and income source.
"""

from pathlib import Path

import pandas as pd

from pipeline.sources.base import DataSource


# ---------------------------------------------------------------------------
# Value maps
# ---------------------------------------------------------------------------

EMPLOYMENT_STATUS_MAP = {
    1: "employed_at_work",
    2: "employed_absent",
    3: "unemployed_layoff",
    4: "unemployed_looking",
    5: "not_in_labor_force",
}

# Major occupation groups (SOC summary)
OCCUPATION_MAP = {
    1: "management",
    2: "professional",
    3: "service",
    4: "sales_office",
    5: "natural_resources",
    6: "construction",
    7: "production",
    8: "transportation",
    9: "military",
}

# Major industry groups (NAICS summary)
INDUSTRY_MAP = {
    1: "agriculture",
    2: "mining",
    3: "construction",
    4: "manufacturing",
    5: "wholesale_trade",
    6: "retail_trade",
    7: "transportation",
    8: "information",
    9: "finance",
    10: "professional_services",
    11: "education_health",
    12: "leisure_hospitality",
    13: "other_services",
    14: "public_administration",
}

UNION_MEMBERSHIP_MAP = {
    1: "member",
    2: "covered_not_member",
    3: "not_covered",
}

# PEHRUSL1: usual hours per week — kept numeric, no map
# Bucketed in harmonize for categorical use

INCOME_SOURCE_MAP = {
    1: "wages_salaries",
    2: "self_employment",
    3: "farm_income",
    4: "social_security",
    5: "supplemental_security",
    6: "public_assistance",
    7: "interest_dividends",
    8: "retirement",
    9: "other",
}


# ---------------------------------------------------------------------------
# Column maps
# ---------------------------------------------------------------------------

_STANDARD_COLUMN_MAP = {
    "employment_status": "PEMLR",
    "occupation": "PRDTOCC1",
    "industry": "PRDTIND1",
    "union_membership": "PEABSRSN",   # NOTE: actual CPS union var is PEUNION
    "hours_worked": "PEHRUSL1",
    "income_source": "HEFAMINC",
    # Match keys
    "age_bracket": "age_bracket",
    "sex": "sex",
    "race": "race",
    "education": "education",
    "state": "state",
}


class CPSSource(DataSource):
    """Current Population Survey data source plugin."""

    name = "cps"

    variables_provided = [
        "employment_status",
        "occupation",
        "industry",
        "union_membership",
        "hours_worked",
        "income_source",
    ]

    match_keys = [
        "age_bracket",
        "sex",
        "race",
        "education",
        "state",
    ]

    update_cycle = "monthly"

    standard_column_map = _STANDARD_COLUMN_MAP

    variable_maps = {
        "employment_status": EMPLOYMENT_STATUS_MAP,
        "occupation": OCCUPATION_MAP,
        "industry": INDUSTRY_MAP,
        "union_membership": UNION_MEMBERSHIP_MAP,
        "income_source": INCOME_SOURCE_MAP,
        # hours_worked: no map, passed through as numeric
    }

    custom_columns: dict = {}

    # ------------------------------------------------------------------
    # harmonize override — skip absent optional columns
    # ------------------------------------------------------------------

    def harmonize(self, df: pd.DataFrame) -> pd.DataFrame:
        """Map CPS columns to standard schema, skipping absent columns."""
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
        """Placeholder: CPS data available from BLS/Census Bureau.

        https://www.census.gov/data/datasets/time-series/demo/cps/cps-basic.html
        Place the CSV at data/raw/cps/ and call clean() with that path.
        """
        raise NotImplementedError(
            "CPS data must be downloaded from "
            "https://www.census.gov/data/datasets/time-series/demo/cps/cps-basic.html. "
            "Place the CSV at data/raw/cps/ and call clean() with that path."
        )

    def clean(self, raw_path) -> pd.DataFrame:
        """Clean raw CPS data.

        Accepts either a file path (str/Path) or a pre-loaded DataFrame.

        Steps:
        1. Load from path or pass through DataFrame.
        2. Drop rows missing all labor market variables.
        3. Return DataFrame ready for harmonize().
        """
        if isinstance(raw_path, pd.DataFrame):
            df = raw_path.copy()
        else:
            df = pd.read_csv(raw_path)

        labor_raw_cols = [
            c for c in ["PEMLR", "PRDTOCC1", "PRDTIND1", "PEHRUSL1"]
            if c in df.columns
        ]
        if labor_raw_cols:
            df = df.dropna(subset=labor_raw_cols, how="all")

        return df
