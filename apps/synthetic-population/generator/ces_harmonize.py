"""Harmonize raw CES 2024 columns into profile-format fields.

Single source of truth for CES→profile mappings used by the population
builder (engine/ces_loader.py keeps its own copy tuned for KNN matching).
"""
import pandas as pd

CURRENT_YEAR = 2026

PARTY_MAP = {1: "strong_dem", 2: "dem", 3: "lean_dem", 4: "independent",
             5: "lean_rep", 6: "rep", 7: "strong_rep", 8: "independent"}
SEX_MAP = {1: "M", 2: "F", 3: "F", 4: "M"}
RACE_MAP = {1: "white", 2: "black", 3: "hispanic", 4: "asian",
            5: "other", 6: "multiracial", 7: "other", 8: "other"}
EDU_MAP = {1: "less_than_hs", 2: "hs_diploma", 3: "some_college",
           4: "some_college", 5: "bachelors", 6: "graduate"}
URBAN_MAP = {1: "urban", 2: "suburban", 3: "suburban", 4: "rural"}


def harmonize_ces(df: pd.DataFrame, current_year: int = CURRENT_YEAR) -> pd.DataFrame:
    out = df.copy()
    out["party_id"] = out["pid7"].map(PARTY_MAP)
    out["sex"] = out["gender4"].map(SEX_MAP)
    out["race_h"] = out["race"].map(RACE_MAP)
    out["education"] = out["educ"].map(EDU_MAP)
    age = current_year - out["birthyr"]
    out["age_bracket"] = pd.cut(
        age, bins=[0, 24, 34, 44, 54, 64, 200],
        labels=["18-24", "25-34", "35-44", "45-54", "55-64", "65+"],
    ).astype(str).replace("nan", None)
    out["urban_rural"] = out["urbancity"].map(URBAN_MAP)
    return out
