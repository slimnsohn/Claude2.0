"""FINRA NFCS (National Financial Capability Study) source plugin.

Provides financial capability variables: literacy score, sophistication,
tax approach, retirement strategy, advisor usage, and insurance coverage.
"""

from pathlib import Path

import pandas as pd

from pipeline.sources.base import DataSource


# ---------------------------------------------------------------------------
# Value maps
# ---------------------------------------------------------------------------

# Financial literacy score: 0–5 quiz questions correct → normalize to 0.0–1.0
FINANCIAL_LITERACY_SCORE_MAP = {
    0: 0.0,
    1: 0.2,
    2: 0.4,
    3: 0.6,
    4: 0.8,
    5: 1.0,
}

# Financial sophistication: self-assessed 1–7 scale
FINANCIAL_SOPHISTICATION_MAP = {
    1: 0.0,
    2: 0.17,
    3: 0.33,
    4: 0.5,
    5: 0.67,
    6: 0.83,
    7: 1.0,
}

TAX_APPROACH_MAP = {
    1: "itemize",
    2: "standard_deduction",
    3: "tax_professional",
    4: "software",
    5: "does_not_file",
    6: "other",
}

RETIREMENT_STRATEGY_MAP = {
    1: "401k_ira",
    2: "pension",
    3: "social_security_only",
    4: "savings_only",
    5: "no_plan",
    6: "other",
}

# Uses financial advisor: yes/no
_BINARY_MAP = {
    1: True,
    2: False,
}

# Insurance coverage: number of types (0=none, up to 4=all major types)
# Kept as integer count; no map
INSURANCE_COVERAGE_MAP = {
    0: "none",
    1: "minimal",
    2: "partial",
    3: "substantial",
    4: "comprehensive",
}


# ---------------------------------------------------------------------------
# Column maps
# ---------------------------------------------------------------------------

_STANDARD_COLUMN_MAP = {
    "financial_literacy_score": "M4",       # NFCS financial literacy quiz score
    "financial_sophistication": "M6",       # Self-assessed financial knowledge
    "tax_approach": "J5",                   # How taxes filed
    "retirement_strategy": "C4A",           # Retirement savings approach
    "uses_financial_advisor": "L1",         # Has financial advisor
    "insurance_coverage": "H1",             # Insurance coverage count
    # Match keys
    "age_bracket": "age_bracket",
    "sex": "sex",
    "race": "race",
    "education": "education",
    "income_bracket": "income_bracket",
}


class FINRANFCSSource(DataSource):
    """FINRA National Financial Capability Study data source plugin."""

    name = "finra_nfcs"

    variables_provided = [
        "financial_literacy_score",
        "financial_sophistication",
        "tax_approach",
        "retirement_strategy",
        "uses_financial_advisor",
        "insurance_coverage",
    ]

    match_keys = [
        "age_bracket",
        "sex",
        "race",
        "education",
        "income_bracket",
    ]

    update_cycle = "triennial"

    standard_column_map = _STANDARD_COLUMN_MAP

    variable_maps = {
        "financial_literacy_score": FINANCIAL_LITERACY_SCORE_MAP,
        "financial_sophistication": FINANCIAL_SOPHISTICATION_MAP,
        "tax_approach": TAX_APPROACH_MAP,
        "retirement_strategy": RETIREMENT_STRATEGY_MAP,
        "uses_financial_advisor": _BINARY_MAP,
        "insurance_coverage": INSURANCE_COVERAGE_MAP,
    }

    custom_columns: dict = {}

    # ------------------------------------------------------------------
    # harmonize override — skip absent optional columns
    # ------------------------------------------------------------------

    def harmonize(self, df: pd.DataFrame) -> pd.DataFrame:
        """Map FINRA NFCS columns to standard schema, skipping absent columns."""
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
        """Placeholder: NFCS data available from FINRA Foundation.

        https://www.usfinancialcapability.org/downloads.php
        Place the CSV at data/raw/finra_nfcs/ and call clean() with that path.
        """
        raise NotImplementedError(
            "NFCS data must be downloaded from "
            "https://www.usfinancialcapability.org/downloads.php. "
            "Place the CSV at data/raw/finra_nfcs/ and call clean() with that path."
        )

    def clean(self, raw_path) -> pd.DataFrame:
        """Clean raw FINRA NFCS data.

        Accepts either a file path (str/Path) or a pre-loaded DataFrame.

        Steps:
        1. Load from path or pass through DataFrame.
        2. Drop rows missing all financial variables.
        3. Return DataFrame ready for harmonize().
        """
        if isinstance(raw_path, pd.DataFrame):
            df = raw_path.copy()
        else:
            df = pd.read_csv(raw_path)

        financial_raw_cols = [
            c for c in ["M4", "M6", "C4A", "L1"]
            if c in df.columns
        ]
        if financial_raw_cols:
            df = df.dropna(subset=financial_raw_cols, how="all")

        return df
