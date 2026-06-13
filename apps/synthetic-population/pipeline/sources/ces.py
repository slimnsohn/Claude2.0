"""CES (Cooperative Election Study) source plugin.

Provides political variables: party identification, ideology, vote choice, and
15 policy position dimensions. Designed for fusion with the ACS backbone via
shared demographic match keys.
"""

from pathlib import Path

import pandas as pd

from pipeline.sources.base import DataSource


# ---------------------------------------------------------------------------
# Value maps
# ---------------------------------------------------------------------------

PARTY_ID_MAP = {
    1: "strong_dem",
    2: "dem",
    3: "lean_dem",
    4: "independent",
    5: "lean_rep",
    6: "rep",
    7: "strong_rep",
}

IDEOLOGY_MAP = {
    1: "very_liberal",
    2: "liberal",
    3: "lean_liberal",
    4: "moderate",
    5: "lean_conservative",
    6: "conservative",
    7: "very_conservative",
}

# ideo5 collapses the 7-point scale; map both so either column works
IDEOLOGY_5PT_MAP = {
    1: "very_liberal",
    2: "liberal",
    3: "moderate",
    4: "conservative",
    5: "very_conservative",
}

VOTE_2020_MAP = {
    1: "biden",
    2: "trump",
    3: "other",
    4: "did_not_vote",
}

VOTE_2024_MAP = {
    1: "harris",
    2: "trump",
    3: "other",
    4: "did_not_vote",
}

# Policy positions: 1=strongly support → 1.0, 4=strongly oppose → 0.0
POLICY_MAP = {
    1: 1.0,
    2: 0.67,
    3: 0.33,
    4: 0.0,
}

# ---------------------------------------------------------------------------
# CES column names → standard names
# ---------------------------------------------------------------------------

# Core political columns
_CORE_COLUMN_MAP = {
    "party_id": "pid7",
    "ideology": "ideo5",
    "vote_2020": "CC20_410",
    "vote_2024": "CC24_410",
}

# Policy position columns (CES module code → standard name)
_POLICY_COLUMN_MAP = {
    "abortion": "CC20_321",
    "gun_control": "CC20_330a",
    "immigration": "CC20_331",
    "climate_policy": "CC20_350",
    "healthcare_system": "CC20_327",
    "government_spending": "CC20_320",
    "trade_policy": "CC20_340",
    "criminal_justice": "CC20_334",
    "education_policy": "CC20_325",
    "social_security": "CC20_326",
    "marijuana": "CC20_332",
    "minimum_wage": "CC20_329",
    "foreign_policy": "CC20_362",
    "tax_policy": "CC20_360",
    "tech_regulation": "CC20_370",
}

# Match-key pass-through columns (already in standard names after clean())
_MATCH_KEY_COLUMNS = {
    "age_bracket": "age_bracket",
    "sex": "sex",
    "race": "race",
    "education": "education",
    "income_bracket": "income_bracket",
    "state": "state",
    "urban_rural": "urban_rural",
}


class CESSource(DataSource):
    """Cooperative Election Study data source plugin."""

    name = "ces"

    variables_provided = [
        "party_id",
        "ideology",
        "vote_2020",
        "vote_2024",
        # 15 policy positions
        "abortion",
        "gun_control",
        "immigration",
        "climate_policy",
        "healthcare_system",
        "government_spending",
        "trade_policy",
        "criminal_justice",
        "education_policy",
        "social_security",
        "marijuana",
        "minimum_wage",
        "foreign_policy",
        "tax_policy",
        "tech_regulation",
    ]

    match_keys = [
        "age_bracket",
        "sex",
        "race",
        "education",
        "income_bracket",
        "state",
        "urban_rural",
    ]

    update_cycle = "election_year"

    # Build the full standard_column_map from the three component dicts
    standard_column_map = {
        **_CORE_COLUMN_MAP,
        **_POLICY_COLUMN_MAP,
        **_MATCH_KEY_COLUMNS,
    }

    # variable_maps: applied by harmonize() when mapping coded values
    variable_maps = {
        "party_id": PARTY_ID_MAP,
        "ideology": IDEOLOGY_5PT_MAP,  # ideo5 is the typical CES column
        "vote_2020": VOTE_2020_MAP,
        "vote_2024": VOTE_2024_MAP,
        # Policy positions
        "abortion": POLICY_MAP,
        "gun_control": POLICY_MAP,
        "immigration": POLICY_MAP,
        "climate_policy": POLICY_MAP,
        "healthcare_system": POLICY_MAP,
        "government_spending": POLICY_MAP,
        "trade_policy": POLICY_MAP,
        "criminal_justice": POLICY_MAP,
        "education_policy": POLICY_MAP,
        "social_security": POLICY_MAP,
        "marijuana": POLICY_MAP,
        "minimum_wage": POLICY_MAP,
        "foreign_policy": POLICY_MAP,
        "tax_policy": POLICY_MAP,
        "tech_regulation": POLICY_MAP,
    }

    custom_columns: dict = {}

    # ------------------------------------------------------------------
    # harmonize override
    # ------------------------------------------------------------------

    def harmonize(self, df: pd.DataFrame) -> pd.DataFrame:
        """Map CES columns to standard schema, skipping absent optional columns.

        The base implementation raises KeyError for any missing source column.
        CES data is modular — not every survey wave includes every question —
        so we skip standard variables whose source column is absent in df.
        """
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
        """Placeholder: CES data must be obtained from Harvard Dataverse.

        Returns the expected raw data directory.  Actual download requires
        a Harvard Dataverse API token and is handled outside this plugin.
        """
        raise NotImplementedError(
            "CES data must be downloaded manually from Harvard Dataverse "
            "(https://dataverse.harvard.edu/dataverse/cces). "
            "Place the CSV at data/raw/ces/ and call clean() with that path."
        )

    def clean(self, raw_path) -> pd.DataFrame:
        """Clean raw CES data.

        Accepts either a file path (str/Path) or a pre-loaded DataFrame
        (used in tests and when data is already in memory).

        Intentionally preserves original CES column names so that
        harmonize() can perform the standard_column_map translation.

        Steps:
        1. Load from path or pass through DataFrame.
        2. Drop rows missing all political variables (by raw column name).
        3. Return DataFrame ready for harmonize().
        """
        if isinstance(raw_path, pd.DataFrame):
            df = raw_path.copy()
        else:
            df = pd.read_csv(raw_path)

        # Drop rows with no political signal at all (check raw CES column names)
        political_raw_cols = [c for c in ["pid7", "ideo5", "CC20_410", "CC24_410"] if c in df.columns]
        if political_raw_cols:
            df = df.dropna(subset=political_raw_cols, how="all")

        return df
