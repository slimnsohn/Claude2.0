"""
Gap-fill the population by sampling real CES respondents who match
underrepresented demographic cells, then running them through the
profile pipeline (plausibility fix, backstory, archetypes).
"""
import json
import uuid
import random
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

registry_path = Path("data/profiles/registry.json")
profiles = json.loads(registry_path.read_text())
df = pd.DataFrame(profiles)
current_n = len(df)
target_n = 1000
need = target_n - current_n
print(f"Current: {current_n}, Target: {target_n}, Need: {need}")

# Load CES data
ces = pd.read_csv("data/raw/ces/ces_2024_common.csv", low_memory=False)

# Harmonize
ces["party_id"] = ces["pid7"].map({
    1: "strong_dem", 2: "dem", 3: "lean_dem", 4: "independent",
    5: "lean_rep", 6: "rep", 7: "strong_rep", 8: "independent",
})
ces["sex"] = ces["gender4"].map({1: "M", 2: "F", 3: "F", 4: "M"})
ces["race_h"] = ces["race"].map({
    1: "white", 2: "black", 3: "hispanic", 4: "asian",
    5: "other", 6: "multiracial", 7: "other", 8: "other",
})
ces["education"] = ces["educ"].map({
    1: "less_than_hs", 2: "hs_diploma", 3: "some_college",
    4: "some_college", 5: "bachelors", 6: "graduate",
})
age = 2026 - ces["birthyr"]
ces["age_bracket"] = pd.cut(
    age, bins=[0, 24, 34, 44, 54, 64, 200],
    labels=["18-24", "25-34", "35-44", "45-54", "55-64", "65+"],
)
ces["urban_rural"] = ces["urbancity"].map({
    1: "urban", 2: "suburban", 3: "suburban", 4: "rural",
})

# Target distributions
targets = {
    "sex": {"M": 0.49, "F": 0.51},
    "race_h": {"white": 0.58, "black": 0.12, "hispanic": 0.19, "asian": 0.06, "other": 0.03, "multiracial": 0.02},
    "education": {"less_than_hs": 0.11, "hs_diploma": 0.27, "some_college": 0.20, "bachelors": 0.22, "graduate": 0.13},
    "age_bracket": {"18-24": 0.12, "25-34": 0.18, "35-44": 0.17, "45-54": 0.16, "55-64": 0.17, "65+": 0.20},
    "party_id": ces["party_id"].value_counts(normalize=True).to_dict(),
    "urban_rural": ces["urban_rural"].dropna().value_counts(normalize=True).to_dict(),
}

# Map current profiles' race to match CES column name for gap calc
df["race_h"] = df["race"]

key_vars = ["race_h", "party_id", "education", "sex", "age_bracket"]
current_cells = df.groupby(key_vars).size().to_dict()

from itertools import product
target_cells = {}
for combo in product(*[targets[v].keys() for v in key_vars]):
    joint_prob = 1.0
    for i, var in enumerate(key_vars):
        joint_prob *= targets[var].get(combo[i], 0.001)
    target_cells[combo] = joint_prob * target_n

deficits = {}
for cell_key, target_count in target_cells.items():
    current_count = current_cells.get(cell_key, 0)
    deficit = target_count - current_count
    if deficit > 0.1:
        deficits[cell_key] = deficit

print(f"Cells with deficits: {len(deficits)}")

ces_clean = ces.dropna(subset=key_vars + ["party_id"]).copy()
ces_clean["_cell"] = list(zip(*[ces_clean[v] for v in key_vars]))
ces_clean["_weight"] = ces_clean["_cell"].map(lambda c: deficits.get(c, 0))
pool = ces_clean[ces_clean["_weight"] > 0].copy()
print(f"CES pool matching deficit cells: {len(pool)} respondents")

if len(pool) < need:
    sampled = pool
    print(f"Warning: pool smaller than need, using all {len(pool)}")
else:
    sampled = pool.sample(n=need, weights="_weight", replace=False, random_state=42)
print(f"Sampled {len(sampled)} CES respondents to fill gaps")

from generator.backstory import generate_backstory
from generator.plausibility import fix_profile

income_map = {}
for v in [1, 2]: income_map[v] = "under-25k"
for v in [3, 4, 5]: income_map[v] = "25-50k"
for v in [6, 7, 8]: income_map[v] = "50-75k"
for v in [9]: income_map[v] = "75-100k"
for v in [10, 11]: income_map[v] = "100-150k"
for v in [12, 13, 14, 15, 16]: income_map[v] = "150k+"
income_map[97] = "50-75k"

ideology_map = {1: "very_liberal", 2: "liberal", 3: "moderate", 4: "conservative", 5: "very_conservative"}

fips_to_abbr = {
    1:"AL",2:"AK",4:"AZ",5:"AR",6:"CA",8:"CO",9:"CT",10:"DE",11:"DC",12:"FL",
    13:"GA",15:"HI",16:"ID",17:"IL",18:"IN",19:"IA",20:"KS",21:"KY",22:"LA",
    23:"ME",24:"MD",25:"MA",26:"MI",27:"MN",28:"MS",29:"MO",30:"MT",31:"NE",
    32:"NV",33:"NH",34:"NJ",35:"NM",36:"NY",37:"NC",38:"ND",39:"OH",40:"OK",
    41:"OR",42:"PA",44:"RI",45:"SC",46:"SD",47:"TN",48:"TX",49:"UT",50:"VT",
    51:"VA",53:"WA",54:"WV",55:"WI",56:"WY",
}

relig_map = {1:"protestant",2:"catholic",3:"mormon",4:"orthodox",5:"jewish",6:"muslim",7:"buddhist",8:"hindu",9:"none",10:"none",11:"none",12:"other"}
attend_map = {1:"weekly",2:"weekly",3:"monthly",4:"rarely",5:"rarely",6:"never"}

news_by_party = {
    "strong_rep": ["fox_news", "newsmax", "local_tv", "fox_news"],
    "rep": ["fox_news", "local_tv", "newsmax", "abc_news"],
    "lean_rep": ["fox_news", "local_tv", "cnn", "abc_news"],
    "independent": ["local_tv", "cnn", "abc_news", "nbc_news"],
    "lean_dem": ["cnn", "nbc_news", "npr", "abc_news"],
    "dem": ["msnbc", "cnn", "npr", "nbc_news"],
    "strong_dem": ["msnbc", "cnn", "npr", "new_york_times"],
}
social_media = ["facebook", "twitter", "instagram", "tiktok", "youtube", "reddit"]

new_profiles = []
for idx, (_, row) in enumerate(sampled.iterrows()):
    if idx % 50 == 0:
        print(f"  Generating profile {idx+1}/{len(sampled)}...")

    age_val = 2026 - row.get("birthyr", 1980)
    income_raw = row.get("faminc_new", 5)
    income_bracket = income_map.get(int(income_raw) if pd.notna(income_raw) else 5, "50-75k")
    income_est = {
        "under-25k": random.randint(12000, 24000),
        "25-50k": random.randint(25000, 49000),
        "50-75k": random.randint(50000, 74000),
        "75-100k": random.randint(75000, 99000),
        "100-150k": random.randint(100000, 149000),
        "150k+": random.randint(150000, 300000),
    }.get(income_bracket, 50000)

    state_fips = row.get("inputstate")
    state = fips_to_abbr.get(int(state_fips) if pd.notna(state_fips) else 0, "TX")

    party = row.get("party_id", "independent")
    news = random.choice(news_by_party.get(party, ["local_tv"]))

    vote_2024_raw = row.get("CC24_410")
    vote_map = {1: "harris", 2: "trump", 3: "other", 4: "did_not_vote", 5: "other"}
    vote_2024 = vote_map.get(int(vote_2024_raw) if pd.notna(vote_2024_raw) else 4, "did_not_vote")

    religpew = row.get("religpew")
    religion = relig_map.get(int(religpew) if pd.notna(religpew) else 11, "none")
    # Check born-again
    if religion == "protestant" and row.get("pew_bornagain") == 1:
        religion = "evangelical"
    elif religion == "protestant":
        religion = "mainline"

    churatd = row.get("pew_churatd")
    attendance = attend_map.get(int(churatd) if pd.notna(churatd) else 5, "rarely")

    profile = {
        "age": int(age_val),
        "age_bracket": str(row.get("age_bracket", "35-44")),
        "sex": row.get("sex", "M"),
        "race": row.get("race_h", "white"),
        "education": row.get("education", "some_college"),
        "income": income_est,
        "income_bracket": income_bracket,
        "state": state,
        "urban_rural": row.get("urban_rural", "suburban"),
        "party_id": party,
        "ideology": ideology_map.get(row.get("ideo5"), "moderate"),
        "vote_2024": vote_2024,
        "religion_affiliation": religion,
        "religion_attendance": attendance,
        "primary_news_source": news,
        "social_media_primary": random.choice(social_media),
        "marital_status": random.choice(["married", "married", "single", "divorced", "widowed"]),
        "veteran_status": "non_veteran",
        "household_size": random.randint(1, 5),
        "children_count": random.randint(0, 3),
        "employment_status": random.choice(["employed", "employed", "employed", "unemployed", "retired"]),
        "homeownership": random.choice(["owned_mortgage", "owned_mortgage", "rented", "rented"]),
        "health_insurance": True,
        "disability": False,
        "citizenship": "citizen_born",
        "native_born": True,
        "commute_mode": random.choice(["car", "car", "car", "public_transit", "remote"]),
        "income_source": random.choice(["wages", "wages", "wages", "self_employment", "retirement"]),
        "occupation": random.choice(["management", "service", "sales", "production", "education", "healthcare", "construction"]),
        "profile_id": str(uuid.uuid4())[:8],
        "batch_id": "ces-gapfill",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "drift_log": [],
    }

    if profile["age"] >= 65:
        profile["employment_status"] = random.choice(["retired", "retired", "employed"])
        profile["income_source"] = random.choice(["retirement", "retirement", "social_security"])
    if profile["age"] < 25:
        profile["marital_status"] = random.choice(["single", "single", "single", "married"])
        profile["homeownership"] = random.choice(["rented", "rented", "rented", "owned_mortgage"])

    fix_profile(profile)
    profile["backstory"] = generate_backstory(profile)
    new_profiles.append(profile)

# Merge and rebuild archetypes
all_profiles = profiles + new_profiles
print(f"\nTotal profiles: {len(all_profiles)}")

from generator.archetypes import ArchetypeBuilder
all_df = pd.DataFrame(all_profiles)
builder = ArchetypeBuilder(min_cell_size=3)
all_df = builder.build(all_df)
for i in range(len(all_profiles)):
    all_profiles[i]["archetype_id"] = all_df.iloc[i]["archetype_id"]

registry_path.write_text(json.dumps(all_profiles, indent=2, default=str))
n_arch = all_df["archetype_id"].nunique()
print(f"Registry saved: {len(all_profiles)} profiles, {n_arch} archetypes")

# Show new distribution vs targets
new_df = pd.DataFrame(all_profiles)
print(f"\n=== DISTRIBUTION ({len(new_df)} profiles) ===")
display_targets = {
    "sex": targets["sex"],
    "race": targets["race_h"],
    "education": targets["education"],
    "age_bracket": targets["age_bracket"],
    "party_id": targets["party_id"],
    "urban_rural": targets["urban_rural"],
}
for var, tgt in display_targets.items():
    print(f"\n{var}:")
    dist = new_df[var].value_counts(normalize=True)
    for val in sorted(tgt.keys()):
        actual = dist.get(val, 0)
        target_pct = tgt[val]
        gap = actual - target_pct
        ok = "OK" if abs(gap) < 0.03 else f"{gap:+.1%}"
        print(f"  {str(val):20s} {actual:6.1%}  target={target_pct:6.1%}  {ok}")
