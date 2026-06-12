"""Build a balanced synthetic population from CES 2024 microdata.

Raking (iterative proportional fitting) computes per-respondent weights so
weighted marginals match census/CES targets, then we sample target_n
respondents without replacement and convert each to a persona profile.
"""
import random
import uuid
from datetime import datetime

import numpy as np
import pandas as pd

from generator.ces_harmonize import harmonize_ces

KEY_VARS = ["sex", "race_h", "education", "age_bracket", "party_id", "urban_rural"]

CENSUS_TARGETS = {
    "sex": {"M": 0.49, "F": 0.51},
    "race_h": {"white": 0.58, "black": 0.12, "hispanic": 0.19,
               "asian": 0.06, "other": 0.03, "multiracial": 0.02},
    "education": {"less_than_hs": 0.11, "hs_diploma": 0.27, "some_college": 0.27,
                  "bachelors": 0.22, "graduate": 0.13},
    "age_bracket": {"18-24": 0.12, "25-34": 0.18, "35-44": 0.17,
                    "45-54": 0.16, "55-64": 0.17, "65+": 0.20},
}


class BalanceError(Exception):
    pass


def compute_targets(harmonized: pd.DataFrame) -> dict:
    """Census targets for demographics; CES-native distributions for party/urban."""
    targets = {k: dict(v) for k, v in CENSUS_TARGETS.items()}
    targets["party_id"] = harmonized["party_id"].value_counts(normalize=True).to_dict()
    targets["urban_rural"] = harmonized["urban_rural"].dropna().value_counts(normalize=True).to_dict()
    return targets


def rake_weights(df: pd.DataFrame, targets: dict, key_vars: list,
                 iterations: int = 20) -> np.ndarray:
    """IPF: adjust weights until weighted marginals match targets. Returns normalized weights."""
    df = df.reset_index(drop=True)
    w = np.ones(len(df))
    for _ in range(iterations):
        for var in key_vars:
            tgt = targets[var]
            vals = df[var]
            for val, t in tgt.items():
                mask = (vals == val).to_numpy()
                cur = w[mask].sum() / w.sum()
                if cur > 0 and t > 0:
                    w[mask] *= t / cur
    return w / w.sum()


INCOME_BRACKET = {}
for v in (1, 2): INCOME_BRACKET[v] = "under-25k"
for v in (3, 4, 5): INCOME_BRACKET[v] = "25-50k"
for v in (6, 7, 8): INCOME_BRACKET[v] = "50-75k"
INCOME_BRACKET[9] = "75-100k"
for v in (10, 11): INCOME_BRACKET[v] = "100-150k"
for v in (12, 13, 14, 15, 16): INCOME_BRACKET[v] = "150k+"
INCOME_BRACKET[97] = "50-75k"

INCOME_RANGE = {"under-25k": (12000, 24000), "25-50k": (25000, 49000),
                "50-75k": (50000, 74000), "75-100k": (75000, 99000),
                "100-150k": (100000, 149000), "150k+": (150000, 300000)}

IDEOLOGY_MAP = {1: "very_liberal", 2: "liberal", 3: "moderate",
                4: "conservative", 5: "very_conservative"}
VOTE_MAP = {1: "harris", 2: "trump", 3: "other", 4: "did_not_vote", 5: "other"}
RELIG_MAP = {1: "protestant", 2: "catholic", 3: "mormon", 4: "orthodox", 5: "jewish",
             6: "muslim", 7: "buddhist", 8: "hindu", 9: "none", 10: "none",
             11: "none", 12: "other"}
ATTEND_MAP = {1: "weekly", 2: "weekly", 3: "monthly", 4: "rarely", 5: "rarely", 6: "never"}
FIPS_TO_ABBR = {1: "AL", 2: "AK", 4: "AZ", 5: "AR", 6: "CA", 8: "CO", 9: "CT", 10: "DE",
                11: "DC", 12: "FL", 13: "GA", 15: "HI", 16: "ID", 17: "IL", 18: "IN",
                19: "IA", 20: "KS", 21: "KY", 22: "LA", 23: "ME", 24: "MD", 25: "MA",
                26: "MI", 27: "MN", 28: "MS", 29: "MO", 30: "MT", 31: "NE", 32: "NV",
                33: "NH", 34: "NJ", 35: "NM", 36: "NY", 37: "NC", 38: "ND", 39: "OH",
                40: "OK", 41: "OR", 42: "PA", 44: "RI", 45: "SC", 46: "SD", 47: "TN",
                48: "TX", 49: "UT", 50: "VT", 51: "VA", 53: "WA", 54: "WV", 55: "WI", 56: "WY"}
NEWS_BY_PARTY = {
    "strong_rep": ["fox_news", "newsmax", "local_tv", "fox_news"],
    "rep": ["fox_news", "local_tv", "newsmax", "abc_news"],
    "lean_rep": ["fox_news", "local_tv", "cnn", "abc_news"],
    "independent": ["local_tv", "cnn", "abc_news", "nbc_news"],
    "lean_dem": ["cnn", "nbc_news", "npr", "abc_news"],
    "dem": ["msnbc", "cnn", "npr", "nbc_news"],
    "strong_dem": ["msnbc", "cnn", "npr", "new_york_times"],
}
SOCIAL_MEDIA = ["facebook", "twitter", "instagram", "tiktok", "youtube", "reddit"]


def _safe_int(val, default):
    try:
        return int(val) if pd.notna(val) else default
    except (TypeError, ValueError):
        return default


def respondent_to_profile(row, batch_id: str, rng: random.Random) -> dict:
    """Convert one harmonized CES row to a persona profile dict.

    Uses the caller-supplied rng for all choices made in this function.
    Downstream helpers (fix_profile, generate_backstory) use the module-level
    random state; we bracket their calls with getstate/setstate so the global
    state is derived from rng and then restored — keeping results reproducible
    without permanently altering the global random state.
    """
    from generator.backstory import generate_backstory
    from generator.plausibility import fix_profile

    age_val = 2026 - _safe_int(row.get("birthyr"), 1980)
    inc_bracket = INCOME_BRACKET.get(_safe_int(row.get("faminc_new"), 5), "50-75k")
    lo, hi = INCOME_RANGE[inc_bracket]
    party = row.get("party_id") or "independent"
    religion = RELIG_MAP.get(_safe_int(row.get("religpew"), 11), "none")
    if religion == "protestant":
        religion = "evangelical" if row.get("pew_bornagain") == 1 else "mainline"

    profile = {
        "age": int(age_val),
        "age_bracket": str(row.get("age_bracket") or "35-44"),
        "sex": row.get("sex") or "M",
        "race": row.get("race_h") or "white",
        "education": row.get("education") or "some_college",
        "income": rng.randint(lo, hi),
        "income_bracket": inc_bracket,
        "state": FIPS_TO_ABBR.get(_safe_int(row.get("inputstate"), 0), "TX"),
        "urban_rural": row.get("urban_rural") or "suburban",
        "party_id": party,
        "ideology": IDEOLOGY_MAP.get(_safe_int(row.get("ideo5"), 3), "moderate"),
        "vote_2024": VOTE_MAP.get(_safe_int(row.get("CC24_410"), 4), "did_not_vote"),
        "religion_affiliation": religion,
        "religion_attendance": ATTEND_MAP.get(_safe_int(row.get("pew_churatd"), 5), "rarely"),
        "primary_news_source": rng.choice(NEWS_BY_PARTY.get(party, ["local_tv"])),
        "social_media_primary": rng.choice(SOCIAL_MEDIA),
        "marital_status": rng.choice(["married", "married", "single", "divorced", "widowed"]),
        "veteran_status": "non_veteran",
        "household_size": rng.randint(1, 5),
        "children_count": rng.randint(0, 3),
        "employment_status": rng.choice(["employed", "employed", "employed", "unemployed", "retired"]),
        "homeownership": rng.choice(["owned_mortgage", "owned_mortgage", "rented", "rented"]),
        "health_insurance": True,
        "disability": False,
        "citizenship": "citizen_born",
        "native_born": True,
        "commute_mode": rng.choice(["car", "car", "car", "public_transit", "remote"]),
        "income_source": rng.choice(["wages", "wages", "wages", "self_employment", "retirement"]),
        "occupation": rng.choice(["management", "service", "sales", "production",
                                  "education", "healthcare", "construction"]),
        "ces_row_id": _safe_int(row.get("caseid"), -1),
        "profile_id": str(uuid.uuid4())[:8],
        "batch_id": batch_id,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "drift_log": [],
        "beliefs": {},
    }
    if profile["age"] >= 65:
        profile["employment_status"] = rng.choice(["retired", "retired", "employed"])
        profile["income_source"] = rng.choice(["retirement", "retirement", "social_security"])
    if profile["age"] < 25:
        profile["marital_status"] = rng.choice(["single", "single", "single", "married"])
        profile["homeownership"] = rng.choice(["rented", "rented", "rented", "owned_mortgage"])

    # fix_profile and generate_backstory use the module-level random state.
    # We derive a deterministic seed from rng so their output is reproducible
    # when respondent_to_profile is called with the same rng seed, then restore
    # the previous global state so we don't corrupt callers.
    _saved_state = random.getstate()
    # Pull a deterministic integer from rng to seed the global random instance
    _deterministic_seed = rng.getrandbits(64)
    random.seed(_deterministic_seed)
    try:
        fix_profile(profile)
        profile["backstory"] = generate_backstory(profile)
    finally:
        random.setstate(_saved_state)

    return profile


def balance_report(profiles: list, targets: dict) -> dict:
    """Compare profile marginals to targets. Profiles use 'race'; targets use 'race_h'."""
    df = pd.DataFrame(profiles)
    if "race_h" not in df.columns and "race" in df.columns:
        df["race_h"] = df["race"]
    report = {"vars": {}, "max_gap": 0.0, "n": len(df)}
    for var, tgt in targets.items():
        dist = df[var].value_counts(normalize=True).to_dict() if var in df.columns else {}
        rows = {}
        for val, t in tgt.items():
            actual = dist.get(val, 0.0)
            gap = actual - t
            rows[str(val)] = {"actual": round(actual, 4), "target": round(t, 4),
                              "gap": round(gap, 4)}
            report["max_gap"] = max(report["max_gap"], abs(gap))
        report["vars"][var] = rows
    return report


def check_balance(report: dict, tolerance: float = 0.03):
    if report["max_gap"] > tolerance:
        raise BalanceError(
            f"Balance gate failed: max marginal gap {report['max_gap']:.3f} > {tolerance}")


def build_population(ces_path: str, target_n: int, batch_id: str,
                     seed: int = 42) -> tuple[list, dict]:
    """Full pipeline: load → harmonize → rake → sample → profiles → report (gate enforced)."""
    ces = pd.read_csv(ces_path, low_memory=False)
    harmonized = harmonize_ces(ces).dropna(subset=KEY_VARS).reset_index(drop=True)
    targets = compute_targets(harmonized)
    weights = rake_weights(harmonized, targets, KEY_VARS)

    np_rng = np.random.default_rng(seed)
    n = min(target_n, len(harmonized))
    idx = np_rng.choice(len(harmonized), size=n, replace=False, p=weights)
    sampled = harmonized.iloc[idx]

    rng = random.Random(seed)
    profiles = []
    for i, (_, row) in enumerate(sampled.iterrows()):
        if i % 500 == 0:
            print(f"  building profile {i + 1}/{n}...")
        profiles.append(respondent_to_profile(row, batch_id, rng))

    report = balance_report(profiles, targets)
    check_balance(report)
    return profiles, report
