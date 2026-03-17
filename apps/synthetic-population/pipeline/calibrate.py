import pandas as pd
import numpy as np


class IPFCalibrator:
    """Iterative Proportional Fitting to match census marginals."""

    def __init__(self, max_iterations: int = 100, tolerance: float = 0.02):
        self.max_iterations = max_iterations
        self.tolerance = tolerance

    def calibrate(self, data: pd.DataFrame, target_marginals: dict) -> pd.DataFrame:
        """
        Adjust record weights so population marginals match targets.

        target_marginals: {variable: {value: proportion}}
        Returns: DataFrame with '_weight' column added.
        """
        result = data.copy()
        n = len(result)
        result["_weight"] = 1.0 / n  # Start with uniform weights

        for iteration in range(self.max_iterations):
            for var, targets in target_marginals.items():
                if var not in result.columns:
                    continue

                for value, target_prop in targets.items():
                    mask = result[var] == value
                    current_prop = result.loc[mask, "_weight"].sum()

                    if current_prop > 0:
                        adjustment = target_prop / current_prop
                        result.loc[mask, "_weight"] *= adjustment

                # Normalize after each variable so proportions stay valid
                weight_sum = result["_weight"].sum()
                if weight_sum > 0:
                    result["_weight"] /= weight_sum

            # Check convergence after full pass across all variables
            max_diff = 0.0
            for var, targets in target_marginals.items():
                if var not in result.columns:
                    continue
                for value, target_prop in targets.items():
                    mask = result[var] == value
                    actual_prop = result.loc[mask, "_weight"].sum()
                    diff = abs(target_prop - actual_prop)
                    max_diff = max(max_diff, diff)

            if max_diff < self.tolerance:
                break

        return result

    def check_marginals(self, data: pd.DataFrame, target_marginals: dict) -> dict:
        """
        Compare weighted marginals against targets.
        Returns: {variable: {value: {"target": float, "actual": float, "diff": float}}}
        """
        report = {}
        for var, targets in target_marginals.items():
            report[var] = {}
            for value, target_prop in targets.items():
                mask = data[var] == value
                actual = data.loc[mask, "_weight"].sum() if "_weight" in data.columns else mask.mean()
                report[var][value] = {
                    "target": target_prop,
                    "actual": round(actual, 4),
                    "diff": round(actual - target_prop, 4),
                }
        return report
