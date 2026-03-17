import numpy as np
from collections import defaultdict


class PollAggregator:
    """Aggregates poll responses with demographic weighting."""

    def __init__(self, archetype_weights: dict):
        """
        archetype_weights: {archetype_id: float} — population weights summing to ~1.0
        """
        self.weights = archetype_weights

    def aggregate(self, responses: list[dict]) -> dict:
        """
        responses: list of {archetype_id, response (yes/no/unsure), confidence (1-10), demographics: {}}

        Returns:
        {
            "distribution": {"yes": float, "no": float, "unsure": float},
            "mean_confidence": float,
            "confidence_interval": {"yes": [lo, hi], "no": [lo, hi], "unsure": [lo, hi]},
            "n_responses": int,
            "n_missing": int,
            "breakdowns": {
                "party_id": {"strong_dem": {"yes": float, ...}, ...},
                ...
            }
        }
        """
        if not responses:
            return {
                "distribution": {"yes": 0, "no": 0, "unsure": 0},
                "mean_confidence": 0,
                "confidence_interval": {},
                "n_responses": 0,
                "n_missing": len(self.weights),
                "breakdowns": {},
            }

        # Weighted distribution
        total_weight = 0
        dist = defaultdict(float)
        confidences = []

        for resp in responses:
            w = self.weights.get(resp["archetype_id"], 0)
            total_weight += w
            dist[resp["response"]] += w
            confidences.append(resp.get("confidence", 5))

        if total_weight > 0:
            for key in dist:
                dist[key] /= total_weight

        # Demographic breakdowns
        breakdowns = {}
        for resp in responses:
            demos = resp.get("demographics", {})
            for demo_var, demo_val in demos.items():
                if demo_var not in breakdowns:
                    breakdowns[demo_var] = defaultdict(lambda: defaultdict(float))
                breakdowns[demo_var][demo_val][resp["response"]] += self.weights.get(resp["archetype_id"], 0)

        # Normalize breakdowns
        for demo_var in breakdowns:
            for demo_val in breakdowns[demo_var]:
                total = sum(breakdowns[demo_var][demo_val].values())
                if total > 0:
                    for resp_type in breakdowns[demo_var][demo_val]:
                        breakdowns[demo_var][demo_val][resp_type] /= total
                breakdowns[demo_var][demo_val] = dict(breakdowns[demo_var][demo_val])
            breakdowns[demo_var] = dict(breakdowns[demo_var])

        # Bootstrap confidence intervals
        ci = self._bootstrap_ci(responses, n_bootstrap=200)

        n_missing = len(self.weights) - len({r["archetype_id"] for r in responses})

        return {
            "distribution": dict(dist),
            "mean_confidence": np.mean(confidences) if confidences else 0,
            "confidence_interval": ci,
            "n_responses": len(responses),
            "n_missing": n_missing,
            "breakdowns": breakdowns,
        }

    def _bootstrap_ci(self, responses, n_bootstrap=200, alpha=0.05):
        """Weighted bootstrap confidence intervals."""
        if len(responses) < 2:
            return {}

        response_types = list(set(r["response"] for r in responses))
        ci = {}

        boot_dists = {rt: [] for rt in response_types}
        for _ in range(n_bootstrap):
            sample = np.random.choice(responses, size=len(responses), replace=True)
            total_w = sum(self.weights.get(r["archetype_id"], 0) for r in sample)
            if total_w == 0:
                continue
            for rt in response_types:
                w = sum(self.weights.get(r["archetype_id"], 0) for r in sample if r["response"] == rt)
                boot_dists[rt].append(w / total_w)

        for rt in response_types:
            if boot_dists[rt]:
                lo = np.percentile(boot_dists[rt], 100 * alpha / 2)
                hi = np.percentile(boot_dists[rt], 100 * (1 - alpha / 2))
                ci[rt] = [round(lo, 4), round(hi, 4)]

        return ci
