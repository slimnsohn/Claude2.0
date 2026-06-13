from pathlib import Path
import pandas as pd
from pipeline.sources.base import DataSource


SEX_MAP = {1: "M", 2: "F"}

RACE_MAP = {
    1: "white",
    2: "black",
    3: "other",
    4: "other",
    5: "other",
    6: "asian",
    7: "other",
    8: "multiracial",
    9: "multiracial",
}

EDUCATION_MAP = {
    **{i: "less_than_hs" for i in range(1, 16)},
    16: "hs_diploma",
    17: "hs_diploma",
    18: "some_college",
    19: "some_college",
    20: "some_college",
    21: "bachelors",
    22: "graduate",
    23: "graduate",
    24: "graduate",
}

MARITAL_MAP = {
    1: "married",
    2: "widowed",
    3: "divorced",
    4: "separated",
    5: "never_married",
}

STATE_FIPS = {
    1: "AL", 2: "AK", 4: "AZ", 5: "AR", 6: "CA", 8: "CO", 9: "CT", 10: "DE",
    11: "DC", 12: "FL", 13: "GA", 15: "HI", 16: "ID", 17: "IL", 18: "IN",
    19: "IA", 20: "KS", 21: "KY", 22: "LA", 23: "ME", 24: "MD", 25: "MA",
    26: "MI", 27: "MN", 28: "MS", 29: "MO", 30: "MT", 31: "NE", 32: "NV",
    33: "NH", 34: "NJ", 35: "NM", 36: "NY", 37: "NC", 38: "ND", 39: "OH",
    40: "OK", 41: "OR", 42: "PA", 44: "RI", 45: "SC", 46: "SD", 47: "TN",
    48: "TX", 49: "UT", 50: "VT", 51: "VA", 53: "WA", 54: "WV", 55: "WI",
    56: "WY", 72: "PR",
}

EMPLOYMENT_MAP = {
    1: "employed",
    2: "employed",
    3: "employed",
    4: "unemployed",
    5: "unemployed",
    6: "not_in_labor_force",
}

COMMUTE_MAP = {
    1: "car",
    2: "car",
    3: "car",
    4: "car",
    5: "car",
    6: "transit",
    7: "transit",
    8: "transit",
    9: "transit",
    10: "bicycle",
    11: "walk",
    12: "other",
}

CITIZENSHIP_MAP = {
    1: "citizen_born",
    2: "citizen_born",
    3: "citizen_born",
    4: "naturalized",
    5: "not_citizen",
}

HOMEOWNERSHIP_MAP = {
    1: "owned_mortgage",
    2: "owned_free",
    3: "rented",
    4: "no_cash_rent",
}


def _age_bracket(age):
    if pd.isna(age):
        return None
    age = int(age)
    if age < 25:
        return "18-24"
    elif age < 35:
        return "25-34"
    elif age < 45:
        return "35-44"
    elif age < 55:
        return "45-54"
    elif age < 65:
        return "55-64"
    else:
        return "65+"


def _income_bracket(income):
    if pd.isna(income):
        return None
    income = float(income)
    if income < 25000:
        return "under-25k"
    elif income < 50000:
        return "25-50k"
    elif income < 75000:
        return "50-75k"
    elif income < 100000:
        return "75-100k"
    elif income < 150000:
        return "100-150k"
    else:
        return "150k+"


class ACSPumsSource(DataSource):
    """ACS Public Use Microdata Sample — demographic backbone source."""

    name = "acs_pums"
    variables_provided = [
        "age",
        "age_bracket",
        "sex",
        "race",
        "education",
        "income",
        "income_bracket",
        "marital_status",
        "state",
        "veteran_status",
        "disability",
        "citizenship",
        "language",
        "household_size",
        "employment_status",
        "homeownership",
        "health_insurance",
        "commute_mode",
    ]
    match_keys = ["age_bracket", "sex", "race", "education"]
    update_cycle = "annual"

    # Not used — harmonize() is fully overridden for PUMS-specific logic.
    standard_column_map = {}
    variable_maps = {}
    custom_columns = {}

    def download(self) -> Path:
        """Placeholder — real download logic added when ACS API integration is built."""
        raise NotImplementedError(
            "ACS PUMS download not yet implemented. "
            "Place raw CSV files in the data/ directory and call clean() directly."
        )

    def clean_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Filter and sanitize a raw PUMS DataFrame.

        - Keeps only persons 18 and older (AGEP >= 18).
        - Converts string-encoded numeric columns to numeric.
        - Leaves NaN in place so harmonize() can handle missing values per-field.
        """
        numeric_cols = [
            "AGEP", "SEX", "RAC1P", "HISP", "SCHL", "PINCP", "MAR",
            "ST", "MIL", "DIS", "CIT", "ENG", "NP", "JWTRNS", "ESR",
            "HINS1", "TEN", "PWGTP",
        ]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df[df["AGEP"] >= 18].copy()
        return df

    def clean(self, raw_path) -> pd.DataFrame:
        """Read a raw PUMS CSV file and return a cleaned DataFrame."""
        df = pd.read_csv(raw_path, low_memory=False)
        return self.clean_dataframe(df)

    def harmonize(self, df: pd.DataFrame) -> pd.DataFrame:
        """Map PUMS columns to the standard schema.

        Overrides base implementation to handle:
        - Hispanic origin override (HISP > 1 takes precedence over RAC1P)
        - Derived age brackets and income brackets
        - State FIPS to 2-letter abbreviation
        - All other PUMS-specific code mappings
        """
        result = pd.DataFrame(index=df.index)

        # Age (raw and bracketed)
        result["age"] = df["AGEP"]
        result["age_bracket"] = df["AGEP"].apply(_age_bracket)

        # Sex
        result["sex"] = df["SEX"].map(SEX_MAP)

        # Race — Hispanic origin overrides RAC1P when HISP > 1
        race = df["RAC1P"].map(RACE_MAP)
        if "HISP" in df.columns:
            hispanic_mask = df["HISP"].notna() & (df["HISP"] > 1)
            race[hispanic_mask] = "hispanic"
        result["race"] = race

        # Education
        result["education"] = df["SCHL"].map(EDUCATION_MAP)

        # Income (raw and bracketed)
        result["income"] = df["PINCP"]
        result["income_bracket"] = df["PINCP"].apply(_income_bracket)

        # Marital status
        result["marital_status"] = df["MAR"].map(MARITAL_MAP)

        # State
        result["state"] = df["ST"].map(STATE_FIPS)

        # Veteran status (MIL: 1=active, 2=veteran, 3=veteran, 4=never served)
        if "MIL" in df.columns:
            result["veteran_status"] = df["MIL"].map(
                {1: "active", 2: "veteran", 3: "veteran", 4: "non_veteran"}
            )

        # Disability (DIS: 1=with disability, 2=without)
        if "DIS" in df.columns:
            result["disability"] = df["DIS"].map({1: True, 2: False})

        # Citizenship
        if "CIT" in df.columns:
            result["citizenship"] = df["CIT"].map(CITIZENSHIP_MAP)

        # Language (ENG: 1=only English, 2=very well, 3=well, 4=not well, 5=not at all)
        if "ENG" in df.columns:
            result["language"] = df["ENG"].map(
                {1: "english_only", 2: "english_very_well",
                 3: "english_well", 4: "english_not_well", 5: "english_not_at_all"}
            )

        # Household size
        if "NP" in df.columns:
            result["household_size"] = df["NP"]

        # Employment status
        if "ESR" in df.columns:
            result["employment_status"] = df["ESR"].map(EMPLOYMENT_MAP)

        # Homeownership
        if "TEN" in df.columns:
            result["homeownership"] = df["TEN"].map(HOMEOWNERSHIP_MAP)

        # Health insurance (HINS1: 1=yes, 2=no)
        if "HINS1" in df.columns:
            result["health_insurance"] = df["HINS1"].map({1: True, 2: False})

        # Commute mode
        if "JWTRNS" in df.columns:
            result["commute_mode"] = df["JWTRNS"].map(COMMUTE_MAP)

        # Person weight — namespaced as a custom column
        if "PWGTP" in df.columns:
            result[f"{self.name}:person_weight"] = df["PWGTP"]

        return result
