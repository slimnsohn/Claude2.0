"""
Build a 1000-profile population directly from CES respondents,
sampling proportional to census demographic targets.
Each profile is a real CES person with backstory generated.
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
random.seed(42)
np.random.seed(42)

# Load CES
print("Loading CES data...")
ces = pd.read_csv("data/raw/ces/ces_2024_common.csv", low_memory=False)
print(f"  {len(ces)} respondents")

# Harmonize demographics
ces["party_id"] = ces["pid7"].map({1:"strong_dem",2:"dem",3:"lean_dem",4:"independent",5:"lean_rep",6:"rep",7:"strong_rep",8:"independent"})
ces["sex"] = ces["gender4"].map({1:"M",2:"F",3:"F",4:"M"})
ces["race_h"] = ces["race"].map({1:"white",2:"black",3:"hispanic",4:"asian",5:"other",6:"multiracial",7:"other",8:"other"})
ces["education"] = ces["educ"].map({1:"less_than_hs",2:"hs_diploma",3:"some_college",4:"some_college",5:"bachelors",6:"graduate"})
age = 2026 - ces["birthyr"]
ces["age_bracket"] = pd.cut(age, bins=[0,24,34,44,54,64,200], labels=["18-24","25-34","35-44","45-54","55-64","65+"])
ces["urban_rural"] = ces["urbancity"].map({1:"urban",2:"suburban",3:"suburban",4:"rural"})

# Target distributions (census for demographics, CES for political)
targets = {
    "sex": {"M": 0.49, "F": 0.51},
    "race_h": {"white": 0.58, "black": 0.12, "hispanic": 0.19, "asian": 0.06, "other": 0.03, "multiracial": 0.02},
    "education": {"less_than_hs": 0.11, "hs_diploma": 0.27, "some_college": 0.20, "bachelors": 0.22, "graduate": 0.13},
    "age_bracket": {"18-24": 0.12, "25-34": 0.18, "35-44": 0.17, "45-54": 0.16, "55-64": 0.17, "65+": 0.20},
}

# Compute per-CES-respondent sampling weight
ces_clean = ces.dropna(subset=["party_id", "sex", "race_h", "education", "age_bracket", "urban_rural"]).copy()
print(f"  {len(ces_clean)} after dropna")

# Weight each CES respondent by how much their demographics are needed
weight_vars = ["sex", "race_h", "education", "age_bracket"]
actual_dists = {v: ces_clean[v].value_counts(normalize=True).to_dict() for v in weight_vars}

sampling_weights = np.ones(len(ces_clean))
for i, (_, row) in enumerate(ces_clean.iterrows()):
    for v in weight_vars:
        actual_pct = actual_dists[v].get(row[v], 0.01)
        target_pct = targets[v].get(row[v], 0.01)
        sampling_weights[i] *= target_pct / actual_pct

sampling_weights /= sampling_weights.sum()

# Sample 1000 respondents
print(f"Sampling {TARGET_N} CES respondents weighted by census targets...")
sampled = ces_clean.sample(n=TARGET_N, weights=sampling_weights, replace=False, random_state=42)
print(f"  Sampled {len(sampled)}")

# Build profiles
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
socials = ["facebook","twitter","instagram","tiktok","youtube","reddit"]
vote_map = {1:"harris",2:"trump",3:"other",4:"did_not_vote",5:"other"}

profiles = []
for idx, (_, row) in enumerate(sampled.iterrows()):
    if idx % 200 == 0:
        print(f"  Building profile {idx+1}/{len(sampled)}...")

    age_val = 2026 - row.get("birthyr", 1980)
    ir = row.get("faminc_new", 5)
    ib = income_map.get(int(ir) if pd.notna(ir) else 5, "50-75k")
    ie = {"under-25k":random.randint(12000,24000),"25-50k":random.randint(25000,49000),"50-75k":random.randint(50000,74000),"75-100k":random.randint(75000,99000),"100-150k":random.randint(100000,149000),"150k+":random.randint(150000,300000)}.get(ib, 50000)
    sf = row.get("inputstate")
    st = fips_to_abbr.get(int(sf) if pd.notna(sf) else 0, "TX")
    pa = row.get("party_id", "independent")
    nw = random.choice(news_by_party.get(pa, ["local_tv"]))
    v24 = row.get("CC24_410")
    vt = vote_map.get(int(v24) if pd.notna(v24) else 4, "did_not_vote")
    rp = row.get("religpew")
    rl = relig_map.get(int(rp) if pd.notna(rp) else 11, "none")
    if rl == "protestant":
        rl = "evangelical" if row.get("pew_bornagain") == 1 else "mainline"
    ca = row.get("pew_churatd")
    at = attend_map.get(int(ca) if pd.notna(ca) else 5, "rarely")

    p = {
        "age": int(age_val),
        "age_bracket": str(row.get("age_bracket", "35-44")),
        "sex": row.get("sex", "M"),
        "race": row.get("race_h", "white"),
        "education": row.get("education", "some_college"),
        "income": ie,
        "income_bracket": ib,
        "state": st,
        "urban_rural": row.get("urban_rural", "suburban"),
        "party_id": pa,
        "ideology": ideology_map.get(row.get("ideo5"), "moderate"),
        "vote_2024": vt,
        "religion_affiliation": rl,
        "religion_attendance": at,
        "primary_news_source": nw,
        "social_media_primary": random.choice(socials),
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
        "batch_id": "ces-balanced-v1",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "drift_log": [],
    }

    if p["age"] >= 65:
        p["employment_status"] = random.choice(["retired", "retired", "employed"])
        p["income_source"] = random.choice(["retirement", "retirement", "social_security"])
    if p["age"] < 25:
        p["marital_status"] = random.choice(["single", "single", "single", "married"])
        p["homeownership"] = random.choice(["rented", "rented", "rented", "owned_mortgage"])

    fix_profile(p)
    p["backstory"] = generate_backstory(p)
    profiles.append(p)

# Assign archetypes
print("\nAssigning archetypes...")
from generator.archetypes import ArchetypeBuilder
all_df = pd.DataFrame(profiles)
builder = ArchetypeBuilder(min_cell_size=3)
all_df = builder.build(all_df)
for i in range(len(profiles)):
    profiles[i]["archetype_id"] = all_df.iloc[i]["archetype_id"]

# Save
registry_path = Path("data/profiles/registry.json")
registry_path.write_text(json.dumps(profiles, indent=2, default=str))
n_arch = all_df["archetype_id"].nunique()
print(f"\nSaved: {len(profiles)} profiles, {n_arch} archetypes")

# Distribution check
nd = pd.DataFrame(profiles)
display = {"sex": targets["sex"], "race": targets["race_h"], "education": targets["education"], "age_bracket": targets["age_bracket"]}
# Add CES-based party
party_target = ces_clean["party_id"].value_counts(normalize=True).to_dict()
urban_target = ces_clean["urban_rural"].value_counts(normalize=True).to_dict()
display["party_id"] = party_target
display["urban_rural"] = urban_target

print(f"\n{'Variable':<15} {'Value':<20} {'Actual':>8} {'Target':>8} {'Gap':>8}")
print("-" * 65)
for var, tgt in display.items():
    dist = nd[var].value_counts(normalize=True)
    for val in sorted(tgt.keys()):
        actual = dist.get(val, 0)
        target_pct = tgt[val]
        gap = actual - target_pct
        marker = "  OK" if abs(gap) < 0.03 else f"  {gap:+.1%}"
        print(f"{var:<15} {str(val):<20} {actual:7.1%} {target_pct:7.1%} {gap:+7.1%}{marker}")
