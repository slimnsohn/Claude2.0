import pandas as pd


class GapAnalyzer:
    """Compares population demographics against target marginals."""

    def __init__(self, target_marginals: dict):
        """
        target_marginals: {variable: {value: proportion}}
        Example: {"sex": {"M": 0.48, "F": 0.52}, "race": {"white": 0.60, ...}}
        """
        self.targets = target_marginals

    def analyze(self, population: pd.DataFrame) -> dict:
        """
        Returns sampling_bias: {variable: {value: weight}}
        Weight > 1.0 means underrepresented (should be sampled more).
        Weight < 1.0 means overrepresented (should be sampled less).
        Weight = 1.0 means on target.
        """
        bias = {}
        for var, target_dist in self.targets.items():
            if var not in population.columns or len(population) == 0:
                # Empty population: all values underrepresented equally
                bias[var] = {val: 2.0 for val in target_dist}
                continue

            actual_dist = population[var].value_counts(normalize=True).to_dict()
            bias[var] = {}
            for val, target_prop in target_dist.items():
                actual_prop = actual_dist.get(val, 0.0)
                if actual_prop == 0:
                    bias[var][val] = 2.0  # max boost
                else:
                    ratio = target_prop / actual_prop
                    bias[var][val] = min(max(ratio, 0.1), 2.0)  # clamp
        return bias

    def summary(self, population: pd.DataFrame) -> list[dict]:
        """Returns list of {variable, value, target, actual, gap} sorted by largest gap."""
        gaps = []
        for var, target_dist in self.targets.items():
            actual_dist = {}
            if var in population.columns and len(population) > 0:
                actual_dist = population[var].value_counts(normalize=True).to_dict()
            for val, target_prop in target_dist.items():
                actual_prop = actual_dist.get(val, 0.0)
                gaps.append({
                    "variable": var,
                    "value": val,
                    "target": target_prop,
                    "actual": round(actual_prop, 4),
                    "gap": round(target_prop - actual_prop, 4),
                })
        return sorted(gaps, key=lambda x: abs(x["gap"]), reverse=True)
