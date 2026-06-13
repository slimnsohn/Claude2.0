import pandas as pd
import numpy as np
from scipy.spatial import KDTree
from sklearn.preprocessing import OrdinalEncoder


class StatisticalMatcher:
    def __init__(self, match_keys: list[str], k: int = 5):
        self.match_keys = match_keys
        self.k = k

    def match(self, backbone: pd.DataFrame, donor: pd.DataFrame,
              variables: list[str]) -> pd.DataFrame:
        # Encode match keys
        encoder = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)
        all_keys = pd.concat([backbone[self.match_keys], donor[self.match_keys]])
        encoder.fit(all_keys)

        backbone_encoded = encoder.transform(backbone[self.match_keys])
        donor_encoded = encoder.transform(donor[self.match_keys])

        # Build KDTree on donor records
        tree = KDTree(donor_encoded)

        # For each backbone record, find k nearest donors, sample one
        result = backbone.copy()
        k = min(self.k, len(donor))
        distances, indices = tree.query(backbone_encoded, k=k)

        for var in variables:
            values = []
            for i in range(len(backbone)):
                neighbor_indices = indices[i] if k > 1 else [indices[i]]
                if isinstance(neighbor_indices, np.integer):
                    neighbor_indices = [neighbor_indices]
                chosen = np.random.choice(neighbor_indices)
                values.append(donor[var].iloc[chosen])
            result[var] = values

        return result
