"""
Integrate Real CES 2024 Data into Synthetic Population
=======================================================
Integrates real political variables from survey data via the
Cooperative Election Study (Harvard Dataverse, 60,000 respondents).

Pipeline:
1. Load CES 2024 CSV, harmonize demographics to match ACS format
2. Use StatisticalMatcher to fuse CES political vars onto our 362 profiles
3. Rebuild archetypes with real party_id distribution
4. Save updated registry

After running this, re-run calibration_test.py to measure improvement.
"""

import json
import shutil
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# CES → ACS demographic mapping
# ---------------------------------------------------------------------------

def map_ces_demographics(df: pd.DataFrame) -> pd.DataFrame:
    """Convert raw CES demographic columns to match ACS profile format."""
    out = pd.DataFrame(index=df.index)

    # age_bracket from birthyr
    current_year = 2026
    age = current_year - df["birthyr"]
    out["age_bracket"] = pd.cut(
        age,
        bins=[0, 24, 34, 44, 54, 64, 200],
        labels=["18-24", "25-34", "35-44", "45-54", "55-64", "65+"],
    )

    # sex from gender4: 1=Man, 2=Woman, 3=Non-binary, 4=Other
    out["sex"] = df["gender4"].map({1: "M", 2: "F", 3: "F", 4: "M"})

    # race: 1=White, 2=Black, 3=Hispanic, 4=Asian, 5=Native, 6=Mixed, 7=Other, 8=Middle Eastern
    out["race"] = df["race"].map({
        1: "white", 2: "black", 3: "hispanic", 4: "asian",
        5: "other", 6: "multiracial", 7: "other", 8: "other",
    })

    # education: 1=No HS, 2=HS grad, 3=Some college, 4=2-yr degree, 5=4-yr degree, 6=Post-grad
    out["education"] = df["educ"].map({
        1: "less_than_hs", 2: "hs_diploma", 3: "some_college",
        4: "some_college", 5: "bachelors", 6: "graduate",
    })

    # income_bracket from faminc_new
    # 1=<10k, 2=10-20k, 3=20-30k, 4=30-40k, 5=40-50k, 6=50-60k,
    # 7=60-70k, 8=70-80k, 9=80-100k, 10=100-120k, 11=120-150k,
    # 12=150-200k, 13=200-250k, 14=250-350k, 15=350-500k, 16=500k+, 97=Prefer not
    income_map = {}
    for v in [1, 2]:
        income_map[v] = "under-25k"
    for v in [3, 4, 5]:
        income_map[v] = "25-50k"
    for v in [6, 7, 8]:
        income_map[v] = "50-75k"
    for v in [9]:
        income_map[v] = "75-100k"
    for v in [10, 11]:
        income_map[v] = "100-150k"
    for v in [12, 13, 14, 15, 16]:
        income_map[v] = "150k+"
    income_map[97] = "50-75k"  # prefer not → median
    out["income_bracket"] = df["faminc_new"].map(income_map)

    # state from inputstate (FIPS codes)
    fips_to_abbr = {
        1: "AL", 2: "AK", 4: "AZ", 5: "AR", 6: "CA", 8: "CO", 9: "CT",
        10: "DE", 11: "DC", 12: "FL", 13: "GA", 15: "HI", 16: "ID", 17: "IL",
        18: "IN", 19: "IA", 20: "KS", 21: "KY", 22: "LA", 23: "ME", 24: "MD",
        25: "MA", 26: "MI", 27: "MN", 28: "MS", 29: "MO", 30: "MT", 31: "NE",
        32: "NV", 33: "NH", 34: "NJ", 35: "NM", 36: "NY", 37: "NC", 38: "ND",
        39: "OH", 40: "OK", 41: "OR", 42: "PA", 44: "RI", 45: "SC", 46: "SD",
        47: "TN", 48: "TX", 49: "UT", 50: "VT", 51: "VA", 53: "WA", 54: "WV",
        55: "WI", 56: "WY",
    }
    out["state"] = df["inputstate"].map(fips_to_abbr)

    # urban_rural from urbancity: 1=City, 2=Suburb, 3=Town, 4=Rural
    out["urban_rural"] = df["urbancity"].map({
        1: "urban", 2: "suburban", 3: "suburban", 4: "rural",
    })

    return out


def map_ces_political(df: pd.DataFrame) -> pd.DataFrame:
    """Extract political variables from CES using standard value maps."""
    out = pd.DataFrame(index=df.index)

    # party_id from pid7
    out["party_id"] = df["pid7"].map({
        1: "strong_dem", 2: "dem", 3: "lean_dem", 4: "independent",
        5: "lean_rep", 6: "rep", 7: "strong_rep", 8: "independent",
    })

    # ideology from ideo5
    out["ideology"] = df["ideo5"].map({
        1: "very_liberal", 2: "liberal", 3: "moderate",
        4: "conservative", 5: "very_conservative",
    })

    # vote_2024 from CC24_410
    out["vote_2024"] = df["CC24_410"].map({
        1: "harris", 2: "trump", 3: "other", 4: "did_not_vote",
        5: "other", 6: "other", 8: "did_not_vote", 9: "did_not_vote",
    })

    # vote_2020 from presvote20post
    if "presvote20post" in df.columns:
        out["vote_2020"] = df["presvote20post"].map({
            1: "biden", 2: "trump", 3: "other", 4: "other",
            5: "other", 6: "did_not_vote",
        })

    # Religion affiliation from religpew
    # 1=Protestant, 2=Roman Catholic, 3=Mormon, 4=Eastern/Greek Orthodox,
    # 5=Jewish, 6=Muslim, 7=Buddhist, 8=Hindu, 9=Atheist, 10=Agnostic,
    # 11=Nothing in particular, 12=Something else
    if "religpew" in df.columns:
        relig_map = {
            1: "protestant", 2: "catholic", 3: "mormon", 4: "orthodox",
            5: "jewish", 6: "muslim", 7: "buddhist", 8: "hindu",
            9: "none", 10: "none", 11: "none", 12: "other",
        }
        out["religion_affiliation"] = df["religpew"].map(relig_map)

        # Refine: born-again/evangelical
        if "pew_bornagain" in df.columns:
            is_evangelical = (df["pew_bornagain"] == 1) & (out["religion_affiliation"] == "protestant")
            out.loc[is_evangelical, "religion_affiliation"] = "evangelical"
            # Keep mainline for non-evangelical protestants
            is_mainline = (out["religion_affiliation"] == "protestant")
            out.loc[is_mainline, "religion_affiliation"] = "mainline"

    # Religion attendance from pew_churatd
    # 1=More than once a week, 2=Once a week, 3=Once or twice a month,
    # 4=A few times a year, 5=Seldom, 6=Never
    if "pew_churatd" in df.columns:
        out["religion_attendance"] = df["pew_churatd"].map({
            1: "weekly", 2: "weekly", 3: "monthly",
            4: "rarely", 5: "rarely", 6: "never",
        })

    return out


# ---------------------------------------------------------------------------
# Main integration
# ---------------------------------------------------------------------------

def integrate():
    data_dir = Path("data")
    ces_path = data_dir / "raw" / "ces" / "ces_2024_common.csv"
    registry_path = data_dir / "profiles" / "registry.json"

    print("Loading CES 2024 data (60,000 respondents)...")
    ces_raw = pd.read_csv(ces_path, low_memory=False)
    print(f"  Loaded {len(ces_raw)} rows, {len(ces_raw.columns)} columns")

    # Map demographics
    print("Mapping demographics to ACS format...")
    ces_demo = map_ces_demographics(ces_raw)
    ces_political = map_ces_political(ces_raw)
    ces_donor = pd.concat([ces_demo, ces_political], axis=1)

    # Drop rows with missing key fields
    ces_donor = ces_donor.dropna(subset=["party_id", "age_bracket", "sex", "race", "education"])
    print(f"  CES donor pool after dropna: {len(ces_donor)} rows")

    # Show real party distribution
    print("\n=== REAL CES Party Distribution ===")
    party_dist = ces_donor["party_id"].value_counts(normalize=True).sort_index()
    for party, pct in party_dist.items():
        print(f"  {party:15s}: {pct*100:5.1f}%")

    # Load existing profiles
    print(f"\nLoading existing profiles from {registry_path}...")
    profiles = json.loads(registry_path.read_text())
    print(f"  {len(profiles)} profiles loaded")

    # Build backbone DataFrame with match keys
    backbone = pd.DataFrame(profiles)
    match_keys = ["age_bracket", "sex", "race", "education", "income_bracket", "urban_rural"]

    # Political variables to fuse from CES
    political_vars = [
        "party_id", "ideology", "vote_2024", "vote_2020",
        "religion_affiliation", "religion_attendance",
    ]
    # Only include vars that exist in donor
    political_vars = [v for v in political_vars if v in ces_donor.columns]

    # Drop donor rows with NaN in match keys (KDTree requires finite values)
    ces_donor = ces_donor.dropna(subset=match_keys)
    print(f"  CES donor pool after dropping NaN match keys: {len(ces_donor)} rows")

    # Also ensure backbone has no NaN in match keys
    backbone_clean = backbone.copy()
    for mk in match_keys:
        if backbone_clean[mk].isna().any():
            # Fill with most common value
            backbone_clean[mk] = backbone_clean[mk].fillna(backbone_clean[mk].mode()[0])

    print(f"\nFusing {len(political_vars)} political variables via statistical matching...")
    print(f"  Match keys: {match_keys}")
    print(f"  Variables: {political_vars}")

    # Use the StatisticalMatcher
    from pipeline.fuse import StatisticalMatcher
    matcher = StatisticalMatcher(match_keys=match_keys, k=10)
    fused = matcher.match(backbone_clean, ces_donor, political_vars)

    # Show new party distribution
    print("\n=== FUSED Party Distribution (our 362 profiles) ===")
    new_party = fused["party_id"].value_counts(normalize=True).sort_index()
    for party, pct in new_party.items():
        print(f"  {party:15s}: {pct*100:5.1f}%")

    # Compare old vs new
    old_party = backbone["party_id"].value_counts(normalize=True).sort_index()
    print("\n=== Comparison: Old Synthetic -> New Real ===")
    all_parties = sorted(set(list(old_party.index) + list(new_party.index)))
    for party in all_parties:
        old = old_party.get(party, 0) * 100
        new = new_party.get(party, 0) * 100
        delta = new - old
        print(f"  {party:15s}: {old:5.1f}% -> {new:5.1f}%  ({delta:+5.1f}pp)")

    # Backup old registry
    backup_path = registry_path.with_suffix(f".backup-{datetime.now().strftime('%Y%m%d%H%M%S')}.json")
    shutil.copy2(registry_path, backup_path)
    print(f"\n  Backed up old registry to {backup_path.name}")

    # Update profiles with fused political data
    for i, row in fused.iterrows():
        for var in political_vars:
            val = row[var]
            if pd.notna(val):
                profiles[i][var] = val
            elif var in profiles[i]:
                # Keep existing if CES didn't have a match (shouldn't happen with k=10)
                pass

    # Save updated registry
    registry_path.write_text(json.dumps(profiles, indent=2))
    print(f"  Saved updated registry with real CES political data")

    # Rebuild archetypes
    print("\nRebuilding archetypes...")
    from generator.archetypes import ArchetypeBuilder
    df_profiles = pd.DataFrame(profiles)
    builder = ArchetypeBuilder(min_cell_size=1)
    df_with_arch = builder.build(df_profiles)
    weights = builder.get_weights()

    # Update archetype_id in profiles
    for i, row in df_with_arch.iterrows():
        profiles[i]["archetype_id"] = row["archetype_id"]

    registry_path.write_text(json.dumps(profiles, indent=2))
    print(f"  {len(weights)} archetypes built")

    print("\nIntegration complete. Run calibration_test.py to measure improvement.")
    return profiles


if __name__ == "__main__":
    integrate()
