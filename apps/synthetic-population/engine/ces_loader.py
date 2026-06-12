"""Load and cache CES 2024 microdata for the opinion engine.

Preprocesses demographics into the same format as synthetic profiles
so KNN matching works directly. Caches the loaded DataFrame and
encoded matrix in memory to avoid re-reading the 180MB CSV on every poll.
"""

import numpy as np
import pandas as pd
from sklearn.preprocessing import OrdinalEncoder
from sklearn.neighbors import KDTree


# Demographic columns used for KNN matching (must match profile fields)
MATCH_KEYS = ["party_id", "education", "age_bracket", "race", "urban_rural"]


class CESLoader:
    def __init__(self, ces_path: str):
        self.ces_path = ces_path
        self._data = None
        self._encoded = None
        self._encoder = None
        self._tree = None

    def get_data(self) -> pd.DataFrame:
        """Return the full preprocessed CES DataFrame. Cached after first load."""
        if self._data is not None:
            return self._data

        from engine.ces_columns import CES_COLUMNS
        issue_cols = list(CES_COLUMNS.keys())
        demo_cols = ["pid7", "educ", "birthyr", "gender4", "race", "urbancity", "faminc_new"]
        all_cols = list(set(demo_cols + issue_cols))

        available = pd.read_csv(self.ces_path, nrows=0).columns.tolist()
        load_cols = [c for c in all_cols if c in available]

        df = pd.read_csv(self.ces_path, usecols=load_cols, low_memory=False)

        # Harmonize demographics to match profile format
        df["party_id"] = df["pid7"].map({
            1: "strong_dem", 2: "dem", 3: "lean_dem", 4: "independent",
            5: "lean_rep", 6: "rep", 7: "strong_rep", 8: "independent",
        })

        df["education"] = df["educ"].map({
            1: "less_than_hs", 2: "hs_diploma", 3: "some_college",
            4: "some_college", 5: "bachelors", 6: "graduate",
        })

        current_year = 2026
        age = current_year - df["birthyr"]
        df["age_bracket"] = pd.cut(
            age, bins=[0, 24, 34, 44, 54, 64, 200],
            labels=["18-24", "25-34", "35-44", "45-54", "55-64", "65+"],
        )

        df["sex"] = df["gender4"].map({1: "M", 2: "F", 3: "F", 4: "M"})

        df["race"] = df["race"].map({
            1: "white", 2: "black", 3: "hispanic", 4: "asian",
            5: "other", 6: "multiracial", 7: "other", 8: "other",
        })

        df["urban_rural"] = df["urbancity"].map({
            1: "urban", 2: "suburban", 3: "suburban", 4: "rural",
        })

        # Drop rows with missing key demographics
        df = df.dropna(subset=MATCH_KEYS).reset_index(drop=True)

        self._data = df
        return df

    def get_encoded_demographics(self) -> tuple[np.ndarray, OrdinalEncoder]:
        """Return (encoded_matrix, encoder) for KNN queries. Cached."""
        if self._encoded is not None:
            return self._encoded, self._encoder

        df = self.get_data()
        self._encoder = OrdinalEncoder(
            handle_unknown="use_encoded_value", unknown_value=-1
        )
        self._encoded = self._encoder.fit_transform(df[MATCH_KEYS])
        return self._encoded, self._encoder

    def get_tree(self) -> KDTree:
        """Return a KDTree built on encoded CES demographics. Cached."""
        if self._tree is not None:
            return self._tree

        encoded, _ = self.get_encoded_demographics()
        self._tree = KDTree(encoded)
        return self._tree
