import pandas as pd
import numpy as np
from collections import Counter

# Variables used for archetype assignment
ARCHETYPE_VARS = ["party_id", "race", "education", "religion_attendance", "urban_rural", "info_ecosystem"]

# Simplified groupings to reduce the 288 theoretical cells
PARTY_GROUPS = {
    "strong_dem": "dem", "dem": "dem", "lean_dem": "dem",
    "independent": "ind",
    "lean_rep": "rep", "rep": "rep", "strong_rep": "rep",
}
RACE_GROUPS = {
    "white": "white", "black": "black", "hispanic": "hispanic",
    "asian": "other", "other": "other", "multiracial": "other",
}
EDUCATION_GROUPS = {
    "less_than_hs": "no_college", "hs_diploma": "no_college", "some_college": "no_college",
    "bachelors": "college", "graduate": "college",
}
RELIGIOSITY_GROUPS = {
    "weekly": "regular", "monthly": "regular",
    "yearly": "not_regular", "seldom": "not_regular", "never": "not_regular",
}
URBAN_GROUPS = {
    "urban": "urban", "suburban": "suburban", "rural": "rural",
}


class ArchetypeBuilder:
    def __init__(self, min_cell_size: int = 5):
        self.min_cell_size = min_cell_size
        self.archetypes = {}  # {archetype_id: {vars..., weight, count}}

    def build(self, profiles: pd.DataFrame) -> pd.DataFrame:
        """Assign archetypes to profiles. Returns profiles with archetype_id column."""
        df = profiles.copy()

        # Create grouped versions of clustering variables
        df["_party_grp"] = df.get("party_id", pd.Series(["ind"] * len(df))).map(PARTY_GROUPS).fillna("ind")
        df["_race_grp"] = df.get("race", pd.Series(["other"] * len(df))).map(RACE_GROUPS).fillna("other")
        df["_edu_grp"] = df.get("education", pd.Series(["no_college"] * len(df))).map(EDUCATION_GROUPS).fillna("no_college")
        df["_rel_grp"] = df.get("religion_attendance", pd.Series(["not_regular"] * len(df))).map(RELIGIOSITY_GROUPS).fillna("not_regular")
        df["_urban_grp"] = df.get("urban_rural", pd.Series(["suburban"] * len(df))).map(URBAN_GROUPS).fillna("suburban")

        grp_cols = ["_party_grp", "_race_grp", "_edu_grp", "_rel_grp", "_urban_grp"]

        # Create composite key
        df["_cell"] = df[grp_cols].apply(lambda r: "|".join(r), axis=1)

        # Count cells
        cell_counts = df["_cell"].value_counts().to_dict()

        # Collapse small cells into nearest larger cell
        small_cells = {c for c, n in cell_counts.items() if n < self.min_cell_size}
        large_cells = {c for c, n in cell_counts.items() if n >= self.min_cell_size}

        cell_map = {}  # {original_cell: assigned_cell}
        for cell in large_cells:
            cell_map[cell] = cell

        for cell in small_cells:
            # Find nearest large cell (most shared group values)
            cell_parts = cell.split("|")
            best_match = None
            best_score = -1
            for lc in large_cells:
                lc_parts = lc.split("|")
                score = sum(a == b for a, b in zip(cell_parts, lc_parts))
                if score > best_score:
                    best_score = score
                    best_match = lc
            cell_map[cell] = best_match if best_match else cell

        df["_assigned_cell"] = df["_cell"].map(cell_map)

        # Assign archetype IDs
        unique_cells = sorted(df["_assigned_cell"].dropna().unique())
        cell_to_id = {cell: f"A-{i+1:03d}" for i, cell in enumerate(unique_cells)}
        df["archetype_id"] = df["_assigned_cell"].map(cell_to_id)

        # Compute weights
        total = len(df)
        self.archetypes = {}
        for cell, arch_id in cell_to_id.items():
            mask = df["_assigned_cell"] == cell
            count = mask.sum()
            parts = cell.split("|")
            self.archetypes[arch_id] = {
                "party": parts[0] if len(parts) > 0 else "",
                "race": parts[1] if len(parts) > 1 else "",
                "education": parts[2] if len(parts) > 2 else "",
                "religiosity": parts[3] if len(parts) > 3 else "",
                "urban_rural": parts[4] if len(parts) > 4 else "",
                "count": int(count),
                "weight": round(count / total, 4),
            }

        # Clean up temp columns
        df.drop(columns=[c for c in df.columns if c.startswith("_")], inplace=True)

        return df

    def get_weights(self) -> dict:
        """Returns {archetype_id: weight}."""
        return {aid: info["weight"] for aid, info in self.archetypes.items()}

    def get_representative(self, profiles: pd.DataFrame, archetype_id: str) -> dict:
        """Return the profile closest to the archetype centroid (most common values)."""
        mask = profiles["archetype_id"] == archetype_id
        subset = profiles[mask]
        if len(subset) == 0:
            raise KeyError(f"No profiles for archetype {archetype_id}")

        # For categorical: find the mode of each variable
        # Score each profile by how many modes it matches
        modes = subset.mode().iloc[0]
        scores = subset.apply(lambda row: sum(row[c] == modes[c] for c in subset.columns if c != "archetype_id"), axis=1)
        return subset.iloc[scores.argmax()].to_dict()
