"""
Aggressively rebalance population to match national demographics.
Strategy:
1. Keep all profiles but compute per-profile resampling weight
2. Downsample overrepresented cells, upsample underrepresented
3. Fill remaining gaps with CES-sourced profiles
Target: 1000 profiles matching census + CES national distributions.
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

TARGET_N = 1000

registry_path = Path("data/profiles/registry.json")
profiles = json.loads(registry_path.read_text())
df = pd.DataFrame(profiles)
print(f"Starting with {len(df)} profiles")

# Target marginals
targets = {
    "sex": {"M": 0.49, "F": 0.51},
    "race": {"white": 0.58, "black": 0.12, "hispanic": 0.19, "asian": 0.06, "other": 0.03, "multiracial": 0.02},
    "education": {"less_than_hs": 0.11, "hs_diploma": 0.27, "some_college": 0.20, "bachelors": 0.22, "graduate": 0.13},
    "age_bracket": {"18-24": 0.12, "25-34": 0.18, "35-44": 0.17, "45-54": 0.16, "55-64": 0.17, "65+": 0.20},
}

# CES targets for party and urban
ces = pd.read_csv("data/raw/ces/ces_2024_common.csv", usecols=["pid7", "urbancity"], nrows=60000, low_memory=False)
ces["party_id"] = ces["pid7"].map({1:"strong_dem",2:"dem",3:"lean_dem",4:"independent",5:"lean_rep",6:"rep",7:"strong_rep",8:"independent"})
ces["urban_rural"] = ces["urbancity"].map({1:"urban",2:"suburban",3:"suburban",4:"rural"})
targets["party_id"] = ces["party_id"].value_counts(normalize=True).to_dict()
targets["urban_rural"] = ces["urban_rural"].dropna().value_counts(normalize=True).to_dict()

# Step 1: Compute per-profile weight based on how over/underrepresented they are
# Weight = product of (target_pct / actual_pct) for each demographic variable
weight_vars = ["sex", "race", "education", "age_bracket", "party_id", "urban_rural"]

actual_dists = {}
for var in weight_vars:
    actual_dists[var] = df[var].value_counts(normalize=True).to_dict()

weights = np.ones(len(df))
for i, row in df.iterrows():
    for var in weight_vars:
        val = row[var]
        actual_pct = actual_dists[var].get(val, 0.01)
        target_pct = targets[var].get(val, 0.01)
        # Ratio clipped to avoid extreme weights
        ratio = min(3.0, max(0.1, target_pct / actual_pct))
        weights[i] *= ratio

# Normalize weights
weights = weights / weights.sum()

# Step 2: Resample 600 profiles from existing population using weights
# (keep diversity, shift distribution toward targets)
keep_n = 350
keep_indices = np.random.choice(len(df), size=keep_n, replace=False, p=weights)
kept_profiles = [profiles[i] for i in sorted(keep_indices)]
print(f"Kept {len(kept_profiles)} reweighted profiles from existing population")

# Step 3: Generate 400 gap-fill profiles from CES
fill_n = TARGET_N - len(kept_profiles)
print(f"Need {fill_n} CES gap-fill profiles")

# Load full CES for gap-fill generation
ces_full = pd.read_csv("data/raw/ces/ces_2024_common.csv", low_memory=False)
ces_full["party_id"] = ces_full["pid7"].map({1:"strong_dem",2:"dem",3:"lean_dem",4:"independent",5:"lean_rep",6:"rep",7:"strong_rep",8:"independent"})
ces_full["sex"] = ces_full["gender4"].map({1:"M",2:"F",3:"F",4:"M"})
ces_full["race_h"] = ces_full["race"].map({1:"white",2:"black",3:"hispanic",4:"asian",5:"other",6:"multiracial",7:"other",8:"other"})
ces_full["education"] = ces_full["educ"].map({1:"less_than_hs",2:"hs_diploma",3:"some_college",4:"some_college",5:"bachelors",6:"graduate"})
age = 2026 - ces_full["birthyr"]
ces_full["age_bracket"] = pd.cut(age, bins=[0,24,34,44,54,64,200], labels=["18-24","25-34","35-44","45-54","55-64","65+"])
ces_full["urban_rural"] = ces_full["urbancity"].map({1:"urban",2:"suburban",3:"suburban",4:"rural"})

# Compute per-CES-respondent weight for gap-filling
kept_df = pd.DataFrame(kept_profiles)
key_vars = ["race", "party_id", "education", "sex", "age_bracket", "urban_rural"]
# Use race_h for CES matching
ces_key_vars = ["race_h", "party_id", "education", "sex", "age_bracket", "urban_rural"]

kept_cells = kept_df.groupby(key_vars).size().to_dict()

# Target cell counts
from itertools import product as iterproduct
target_cells = {}
for combo in iterproduct(*[targets[v].keys() for v in key_vars]):
    joint = 1.0
    for i, var in enumerate(key_vars):
        joint *= targets[var].get(combo[i], 0.001)
    target_cells[combo] = joint * TARGET_N

deficits = {}
for cell_key, target_count in target_cells.items():
    current = kept_cells.get(cell_key, 0)
    deficit = target_count - current
    if deficit > 0.1:
        deficits[cell_key] = deficit

ces_clean = ces_full.dropna(subset=ces_key_vars).copy()
ces_clean["_cell"] = list(zip(*[ces_clean[v] for v in ces_key_vars]))
ces_clean["_weight"] = ces_clean["_cell"].map(lambda c: deficits.get(c, 0))
pool = ces_clean[ces_clean["_weight"] > 0].copy()
print(f"CES gap-fill pool: {len(pool)} respondents across {len(deficits)} deficit cells")

sampled = pool.sample(n=min(fill_n, len(pool)), weights="_weight", replace=False, random_state=42)
print(f"Sampled {len(sampled)} CES respondents")

# Build profiles from CES respondents
from generator.backstory import generate_backstory
from generator.plausibility import fix_profile

income_map = {}
for v in [1,2]: income_map[v] = "under-25k"
for v in [3,4,5]: income_map[v] = "25-50k"
for v in [6,7,8]: income_map[v] = "50-75k"
for v in [9]: income_map[v] = "75-100k"
for v in [10,11]: income_map[v] = "100-150k"
for v in [12,13,14,15,16]: income_map[v] = "150k+"
income_map[97] = "50-75k"

ideology_map = {1:"very_liberal",2:"liberal",3:"moderate",4:"conservative",5:"very_conservative"}
fips_to_abbr = {1:"AL",2:"AK",4:"AZ",5:"AR",6:"CA",8:"CO",9:"CT",10:"DE",11:"DC",12:"FL",13:"GA",15:"HI",16:"ID",17:"IL",18:"IN",19:"IA",20:"KS",21:"KY",22:"LA",23:"ME",24:"MD",25:"MA",26:"MI",27:"MN",28:"MS",29:"MO",30:"MT",31:"NE",32:"NV",33:"NH",34:"NJ",35:"NM",36:"NY",37:"NC",38:"ND",39:"OH",40:"OK",41:"OR",42:"PA",44:"RI",45:"SC",46:"SD",47:"TN",48:"TX",49:"UT",50:"VT",51:"VA",53:"WA",54:"WV",55:"WI",56:"WY"}
relig_map = {1:"protestant",2:"catholic",3:"mormon",4:"orthodox",5:"jewish",6:"muslim",7:"buddhist",8:"hindu",9:"none",10:"none",11:"none",12:"other"}
attend_map = {1:"weekly",2:"weekly",3:"monthly",4:"rarely",5:"rarely",6:"never"}
news_by_party = {"strong_rep":["fox_news","newsmax","local_tv"],"rep":["fox_news","local_tv","newsmax"],"lean_rep":["fox_news","local_tv","cnn"],"independent":["local_tv","cnn","abc_news"],"lean_dem":["cnn","nbc_news","npr"],"dem":["msnbc","cnn","npr"],"strong_dem":["msnbc","cnn","npr","new_york_times"]}
social_media = ["facebook","twitter","instagram","tiktok","youtube","reddit"]
vote_map = {1:"harris",2:"trump",3:"other",4:"did_not_vote",5:"other"}

new_profiles = []
for idx, (_, row) in enumerate(sampled.iterrows()):
    if idx % 100 == 0:
        print(f"  Building profile {idx+1}/{len(sampled)}...")

    age_val = 2026 - row.get("birthyr", 1980)
    inc_raw = row.get("faminc_new", 5)
    inc_bracket = income_map.get(int(inc_raw) if pd.notna(inc_raw) else 5, "50-75k")
    inc_est = {"under-25k":random.randint(12000,24000),"25-50k":random.randint(25000,49000),"50-75k":random.randint(50000,74000),"75-100k":random.randint(75000,99000),"100-150k":random.randint(100000,149000),"150k+":random.randint(150000,300000)}.get(inc_bracket, 50000)
    st = fips_to_abbr.get(int(row.get("inputstate",0)) if pd.notna(row.get("inputstate")) else 0, "TX")
    party = row.get("party_id", "independent")
    news = random.choice(news_by_party.get(party, ["local_tv"]))
    v24 = row.get("CC24_410")
    vote = vote_map.get(int(v24) if pd.notna(v24) else 4, "did_not_vote")
    rp = row.get("religpew")
    religion = relig_map.get(int(rp) if pd.notna(rp) else 11, "none")
    if religion == "protestant":
        religion = "evangelical" if row.get("pew_bornagain") == 1 else "mainline"
    ca = row.get("pew_churatd")
    attendance = attend_map.get(int(ca) if pd.notna(ca) else 5, "rarely")

    profile = {
        "age": int(age_val), "age_bracket": str(row.get("age_bracket","35-44")),
        "sex": row.get("sex","M"), "race": row.get("race_h","white"),
        "education": row.get("education","some_college"),
        "income": inc_est, "income_bracket": inc_bracket,
        "state": st, "urban_rural": row.get("urban_rural","suburban"),
        "party_id": party, "ideology": ideology_map.get(row.get("ideo5"), "moderate"),
        "vote_2024": vote,
        "religion_affiliation": religion, "religion_attendance": attendance,
        "primary_news_source": news,
        "social_media_primary": random.choice(social_media),
        "marital_status": random.choice(["married","married","single","divorced","widowed"]),
        "veteran_status": "non_veteran",
        "household_size": random.randint(1,5), "children_count": random.randint(0,3),
        "employment_status": random.choice(["employed","employed","employed","unemployed","retired"]),
        "homeownership": random.choice(["owned_mortgage","owned_mortgage","rented","rented"]),
        "health_insurance": True, "disability": False,
        "citizenship": "citizen_born", "native_born": True,
        "commute_mode": random.choice(["car","car","car","public_transit","remote"]),
        "income_source": random.choice(["wages","wages","wages","self_employment","retirement"]),
        "occupation": random.choice(["management","service","sales","production","education","healthcare","construction"]),
        "profile_id": str(uuid.uuid4())[:8], "batch_id": "ces-rebalance",
        "created_at": datetime.now().isoformat(), "updated_at": datetime.now().isoformat(),
        "drift_log": [],
    }
    if profile["age"] >= 65:
        profile["employment_status"] = random.choice(["retired","retired","employed"])
        profile["income_source"] = random.choice(["retirement","retirement","social_security"])
    if profile["age"] < 25:
        profile["marital_status"] = random.choice(["single","single","single","married"])
        profile["homeownership"] = random.choice(["rented","rented","rented","owned_mortgage"])

    fix_profile(profile)
    profile["backstory"] = generate_backstory(profile)
    new_profiles.append(profile)

all_profiles = kept_profiles + new_profiles
print(f"\nFinal population: {len(all_profiles)} profiles")

from generator.archetypes import ArchetypeBuilder
all_df = pd.DataFrame(all_profiles)
builder = ArchetypeBuilder(min_cell_size=3)
all_df = builder.build(all_df)
for i in range(len(all_profiles)):
    all_profiles[i]["archetype_id"] = all_df.iloc[i]["archetype_id"]

registry_path.write_text(json.dumps(all_profiles, indent=2, default=str))
n_arch = all_df["archetype_id"].nunique()
print(f"Saved: {len(all_profiles)} profiles, {n_arch} archetypes\n")

# Final distribution check
new_df = pd.DataFrame(all_profiles)
display_targets = {"sex": targets["sex"], "race": targets["race"], "education": targets["education"], "age_bracket": targets["age_bracket"], "party_id": targets["party_id"], "urban_rural": targets["urban_rural"]}
for var, tgt in display_targets.items():
    print(f"\n{var}:")
    dist = new_df[var].value_counts(normalize=True)
    for val in sorted(tgt.keys()):
        actual = dist.get(val, 0)
        target_pct = tgt[val]
        gap = actual - target_pct
        ok = "OK" if abs(gap) < 0.03 else f"{gap:+.1%}"
        print(f"  {str(val):20s} {actual:6.1%}  target={target_pct:6.1%}  {ok}")
