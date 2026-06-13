"""Fed SCF (Survey of Consumer Finances) source plugin.

Provides wealth and financial behavior variables: risk tolerance,
investment types, debt level, savings months, plus custom namespaced
variables for net worth bracket and financial planning horizon.
"""

from pathlib import Path

import pandas as pd

from pipeline.sources.base import DataSource


# ---------------------------------------------------------------------------
# Value maps
# ---------------------------------------------------------------------------

# WILLINGNESS TO TAKE FINANCIAL RISK: 1=take substantial risk, 4=take no risk
RISK_TOLERANCE_MAP = {
    1: 1.0,    # take substantial financial risks for substantial gains
    2: 0.67,   # take above-average financial risks
    3: 0.33,   # take average financial risks
    4: 0.0,    # not willing to take any financial risk
}

# Investment types: coded as comma-separated flags in raw data;
# clean() normalizes to a primary type
INVESTMENT_TYPES_MAP = {
    1: "stocks",
    2: "bonds",
    3: "mutual_funds",
    4: "real_estate",
    5: "retirement_accounts",
    6: "savings_accounts",
    7: "business",
    8: "none",
}

# Debt level: SCF provides total debt quintile; map quintile to label
DEBT_LEVEL_MAP = {
    1: "none_to_low",
    2: "low",
    3: "moderate",
    4: "high",
    5: "very_high",
}

# Savings months: how many months expenses covered by savings (winsorized 0–24+)
# Kept as numeric, no map — passed through directly

# ---------------------------------------------------------------------------
# Custom column value maps
# ---------------------------------------------------------------------------

# Net worth bracket: quintile-based
NET_WORTH_BRACKET_MAP = {
    1: "negative_to_zero",
    2: "low",
    3: "middle",
    4: "upper_middle",
    5: "high",
    6: "very_high",
}

# Financial planning horizon
FINANCIAL_PLANNING_HORIZON_MAP = {
    1: "next_few_months",
    2: "next_year",
    3: "next_few_years",
    4: "next_5_10_years",
    5: "longer_than_10_years",
}


# ---------------------------------------------------------------------------
# Column maps
# ---------------------------------------------------------------------------

_STANDARD_COLUMN_MAP = {
    "risk_tolerance": "RISKTOL",
    "investment_types": "HFINX",       # SCF primary financial asset type
    "debt_level": "DEBT_QUINTILE",     # Derived quintile column after clean()
    "savings_months": "SAVEMONTHS",    # Derived savings buffer months
    # Match keys
    "age_bracket": "age_bracket",
    "sex": "sex",
    "race": "race",
    "education": "education",
    "income_bracket": "income_bracket",
}

_CUSTOM_COLUMNS = {
    "net_worth_bracket": "NW_BRACKET",
    "financial_planning_horizon": "PLANNING",
}


class FedSCFSource(DataSource):
    """Federal Reserve Survey of Consumer Finances data source plugin."""

    name = "fed_scf"

    variables_provided = [
        "risk_tolerance",
        "investment_types",
        "debt_level",
        "savings_months",
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
        "risk_tolerance": RISK_TOLERANCE_MAP,
        "investment_types": INVESTMENT_TYPES_MAP,
        "debt_level": DEBT_LEVEL_MAP,
        # savings_months: numeric, no map
    }

    custom_columns = _CUSTOM_COLUMNS

    # Custom maps for namespaced columns
    _custom_variable_maps = {
        "net_worth_bracket": NET_WORTH_BRACKET_MAP,
        "financial_planning_horizon": FINANCIAL_PLANNING_HORIZON_MAP,
    }

    # ------------------------------------------------------------------
    # harmonize override — apply maps to custom columns too
    # ------------------------------------------------------------------

    def harmonize(self, df: pd.DataFrame) -> pd.DataFrame:
        """Map Fed SCF columns to standard schema with custom column mapping."""
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
        """Placeholder: SCF data available from Federal Reserve Board.

        https://www.federalreserve.gov/econres/scfindex.htm
        Place the CSV at data/raw/fed_scf/ and call clean() with that path.
        """
        raise NotImplementedError(
            "SCF data must be downloaded from "
            "https://www.federalreserve.gov/econres/scfindex.htm. "
            "Place the CSV at data/raw/fed_scf/ and call clean() with that path."
        )

    def clean(self, raw_path) -> pd.DataFrame:
        """Clean raw Fed SCF data.

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

        finance_raw_cols = [
            c for c in ["RISKTOL", "HFINX", "DEBT_QUINTILE", "SAVEMONTHS"]
            if c in df.columns
        ]
        if finance_raw_cols:
            df = df.dropna(subset=finance_raw_cols, how="all")

        return df
