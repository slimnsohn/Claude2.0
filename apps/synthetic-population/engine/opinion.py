"""Bottom-up opinion engine using real CES microdata.

Instead of hardcoded party-line curves, this engine:
1. Maps the question to a CES survey column
2. Finds K most demographically similar real CES respondents
3. Reads their actual survey answers
4. Returns a stochastic opinion sampled from the real distribution

Opinions emerge from the bottom up — the aggregate is whatever
the population's composition produces, not a tuned target.
"""

import random
from typing import Optional

import numpy as np
import pandas as pd

from engine.ces_columns import CES_COLUMNS, match_question
from engine.ces_loader import CESLoader, MATCH_KEYS


DEFAULT_K = 50


class OpinionEngine:
    def __init__(self, ces_path: str, k: int = DEFAULT_K):
        self.loader = CESLoader(ces_path)
        self.k = k

    def get_opinion(
        self, question: str, profile: dict, world_shifts: dict = None
    ) -> Optional[tuple[str, int, str]]:
        """Get a stochastic opinion for this profile on this question.

        Returns (opinion, confidence, reasoning) or None if question
        has no CES coverage.
        """
        dist = self.get_distribution(question, profile, world_shifts)
        if dist is None:
            return None

        yes_p = dist["yes"]
        no_p = dist["no"]
        unsure_p = dist["unsure"]

        # Stochastic sample from the real distribution
        roll = random.random()
        if roll < yes_p:
            opinion = "yes"
        elif roll < yes_p + no_p:
            opinion = "no"
        else:
            opinion = "unsure"

        # Confidence derived from how lopsided the distribution is
        dominant = max(yes_p, no_p, unsure_p)
        if dominant > 0.8:
            base_conf = random.randint(7, 10)
        elif dominant > 0.6:
            base_conf = random.randint(5, 8)
        else:
            base_conf = random.randint(3, 6)
        if opinion == "unsure":
            base_conf = min(base_conf, 4)

        # Reasoning
        n = dist.get("_n_neighbors", 0)
        col_name = dist.get("_col_name", "survey data")
        party = profile.get("party_id", "unknown")
        reasoning = (
            f"Based on {n} similar CES respondents "
            f"(matched on demographics), "
            f"{yes_p:.0%} said yes, {no_p:.0%} said no, "
            f"{unsure_p:.0%} unsure. "
            f"This {party.replace('_', ' ')} respondent says {opinion}."
        )

        return opinion, base_conf, reasoning

    def get_distribution(
        self, question: str, profile: dict, world_shifts: dict = None
    ) -> Optional[dict]:
        """Get the yes/no/unsure probability distribution for this profile.

        Returns dict with keys: yes, no, unsure, _n_neighbors, _col_name.
        Returns None if question has no CES coverage.
        """
        col_match = match_question(question)
        if col_match is None:
            return None

        col_id = col_match["col_id"]
        interpret = col_match["interpret"]

        ces_df = self.loader.get_data()
        if col_id not in ces_df.columns:
            return None

        tree = self.loader.get_tree()
        _, encoder = self.loader.get_encoded_demographics()

        # Encode this profile's demographics
        profile_row = pd.DataFrame([{k: profile.get(k, "") for k in MATCH_KEYS}])
        try:
            profile_encoded = encoder.transform(profile_row)
        except Exception:
            return None

        # KNN query
        k = min(self.k, len(ces_df))
        distances, indices = tree.query(profile_encoded, k=k)
        neighbor_indices = indices[0]

        # Read their actual answers
        answers = ces_df.iloc[neighbor_indices][col_id].dropna()
        if len(answers) < 5:
            return None

        # Interpret coded values to yes/no/unsure
        interpreted = answers.apply(interpret)
        counts = interpreted.value_counts()
        total = len(interpreted)

        yes_p = counts.get("yes", 0) / total
        no_p = counts.get("no", 0) / total
        unsure_p = counts.get("unsure", 0) / total

        # Apply world update shifts
        if world_shifts:
            party = profile.get("party_id", "independent")
            party_group = (
                "dem" if party in ("strong_dem", "dem", "lean_dem")
                else "rep" if party in ("strong_rep", "rep", "lean_rep")
                else "independent"
            )
            ws = world_shifts.get(party_group, 0.0)
            if ws != 0:
                yes_p += ws
                no_p -= ws * 0.7
                unsure_p -= ws * 0.3

        # Normalize and clamp
        total_p = yes_p + no_p + unsure_p
        if total_p > 0:
            yes_p /= total_p
            no_p /= total_p
            unsure_p /= total_p

        yes_p = max(0.0, min(1.0, yes_p))
        no_p = max(0.0, min(1.0, no_p))
        unsure_p = max(0.0, min(1.0, unsure_p))

        return {
            "yes": yes_p,
            "no": no_p,
            "unsure": unsure_p,
            "_n_neighbors": len(answers),
            "_col_name": col_match["name"],
            "_col_id": col_id,
        }
