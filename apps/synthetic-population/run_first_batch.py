"""
Run First Batch — Download real ACS PUMS data, fit model, generate 50 profiles.

Usage:
    cd apps/synthetic-population
    python run_first_batch.py
"""
import sys
import json
import time
from pathlib import Path
import pandas as pd
import requests

# Ensure project imports work
sys.path.insert(0, str(Path(__file__).parent))

from pipeline.sources.acs_pums import ACSPumsSource
from pipeline.fit_model import ModelTrainer
from generator.generate import ProfileGenerator
from generator.archetypes import ArchetypeBuilder


# Census API endpoint for ACS 1-Year PUMS (2022)
CENSUS_API_BASE = "https://api.census.gov/data/2022/acs/acs1/pums"

# PUMS variables we need
PUMS_VARS = [
    "AGEP", "SEX", "RAC1P", "HISP", "SCHL", "PINCP", "MAR",
    "ST", "MIL", "DIS", "CIT", "ENG", "NP", "JWTRNS", "ESR",
    "HINS1", "TEN", "PWGTP",
]

# States to pull (FIPS codes) — start with a diverse sample
SAMPLE_STATES = [
    "06",  # CA
    "12",  # FL
    "13",  # GA
    "17",  # IL
    "26",  # MI
    "36",  # NY
    "39",  # OH
    "44",  # RI (small state for variety)
    "48",  # TX
    "53",  # WA
]


def download_pums_state(state_fips: str, max_records: int = 2000) -> pd.DataFrame:
    """Download PUMS records for one state via Census API."""
    # Census API doesn't need a key for moderate usage
    get_vars = ",".join(PUMS_VARS)
    url = f"{CENSUS_API_BASE}?get={get_vars}&for=state:{state_fips}"

    print(f"  Fetching state {state_fips}...", end=" ", flush=True)
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()

    data = resp.json()
    header = data[0]
    rows = data[1:]

    df = pd.DataFrame(rows, columns=header)

    # Convert numeric columns
    for col in PUMS_VARS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Sample down if too large
    if len(df) > max_records:
        df = df.sample(n=max_records, random_state=42, weights="PWGTP" if "PWGTP" in df.columns else None)

    print(f"{len(df)} records")
    return df


def download_all_states() -> pd.DataFrame:
    """Download PUMS data for all sample states."""
    print("Step 1: Downloading ACS PUMS data from Census Bureau API...")
    frames = []
    for fips in SAMPLE_STATES:
        try:
            df = download_pums_state(fips)
            frames.append(df)
            time.sleep(0.5)  # Be polite to the API
        except Exception as e:
            print(f"  WARNING: Failed for state {fips}: {e}")

    if not frames:
        raise RuntimeError("Could not download any PUMS data")

    combined = pd.concat(frames, ignore_index=True)
    print(f"  Total: {len(combined)} records from {len(frames)} states\n")
    return combined


def harmonize_pums(raw_df: pd.DataFrame) -> pd.DataFrame:
    """Run through ACS PUMS source plugin."""
    print("Step 2: Harmonizing PUMS data...")
    source = ACSPumsSource()
    cleaned = source.clean_dataframe(raw_df)
    harmonized = source.harmonize(cleaned)

    # Drop rows with too many NAs
    critical = ["age", "sex", "race", "education", "state"]
    harmonized = harmonized.dropna(subset=critical)

    print(f"  {len(harmonized)} valid records after harmonization")
    print(f"  Sex: {harmonized['sex'].value_counts().to_dict()}")
    print(f"  Race: {harmonized['race'].value_counts().to_dict()}")
    print(f"  Education: {harmonized['education'].value_counts().to_dict()}")
    print()
    return harmonized


def add_synthetic_political_vars(df: pd.DataFrame) -> pd.DataFrame:
    """
    Since we don't have real CES data yet, add plausible political variables
    based on demographic correlations. This is a placeholder until real fusion.
    """
    import numpy as np
    print("Step 3: Adding synthetic political variables (placeholder until CES fusion)...")
    np.random.seed(42)
    n = len(df)

    # Party ID — correlated with race and education
    party_probs = []
    for _, row in df.iterrows():
        if row.get("race") == "black":
            probs = [0.40, 0.25, 0.15, 0.08, 0.05, 0.04, 0.03]
        elif row.get("race") == "hispanic":
            probs = [0.20, 0.20, 0.15, 0.15, 0.10, 0.10, 0.10]
        elif row.get("education") == "graduate":
            probs = [0.20, 0.15, 0.15, 0.15, 0.12, 0.12, 0.11]
        elif row.get("education") in ("less_than_hs", "hs_diploma"):
            probs = [0.08, 0.08, 0.10, 0.15, 0.18, 0.20, 0.21]
        else:
            probs = [0.14, 0.14, 0.14, 0.16, 0.14, 0.14, 0.14]
        party_probs.append(probs)

    parties = ["strong_dem", "dem", "lean_dem", "independent", "lean_rep", "rep", "strong_rep"]
    df["party_id"] = [np.random.choice(parties, p=p) for p in party_probs]

    # Religion — correlated with race and state
    religion_opts = ["evangelical", "mainline", "catholic", "none", "other"]
    religion_probs = []
    for _, row in df.iterrows():
        if row.get("race") == "hispanic":
            probs = [0.10, 0.05, 0.50, 0.25, 0.10]
        elif row.get("race") == "black":
            probs = [0.35, 0.20, 0.05, 0.25, 0.15]
        elif row.get("education") == "graduate":
            probs = [0.10, 0.15, 0.15, 0.45, 0.15]
        else:
            probs = [0.25, 0.15, 0.20, 0.30, 0.10]
        religion_probs.append(probs)

    df["religion_affiliation"] = [np.random.choice(religion_opts, p=p) for p in religion_probs]

    attend_opts = ["weekly", "monthly", "never"]
    df["religion_attendance"] = np.where(
        df["religion_affiliation"] == "none", "never",
        np.random.choice(attend_opts, size=n, p=[0.3, 0.3, 0.4])
    )

    # Urban/rural — correlated with state
    urban_opts = ["urban", "suburban", "rural"]
    df["urban_rural"] = np.random.choice(urban_opts, size=n, p=[0.35, 0.40, 0.25])

    # Income source
    df["income_source"] = np.where(
        df["employment_status"] == "not_in_labor_force", "retirement",
        np.random.choice(["wages", "self_employment"], size=n, p=[0.88, 0.12])
    )

    # Occupation placeholder
    occ_opts = ["professional", "service", "sales", "construction", "production", "management", "other"]
    df["occupation"] = np.random.choice(occ_opts, size=n)

    # Marital-related
    df["children_count"] = np.random.choice([0, 1, 2, 3], size=n, p=[0.3, 0.25, 0.25, 0.2])

    print(f"  Added party_id, religion, urban_rural, income_source, occupation")
    print(f"  Party distribution: {df['party_id'].value_counts().to_dict()}")
    print()
    return df


def fit_and_save_model(df: pd.DataFrame, model_path: str) -> None:
    """Fit SDV model on the prepared data."""
    print("Step 4: Fitting SDV GaussianCopulaSynthesizer...")

    # Identify column types
    categorical = [c for c in df.columns if df[c].dtype == 'object' or df[c].dtype == 'bool']
    numerical = [c for c in df.columns if c not in categorical and ":" not in c]

    # Remove the person weight column — it's for weighting, not synthesis
    df = df.drop(columns=[c for c in df.columns if ":" in c], errors="ignore")

    # Drop columns with too many unique values that SDV might misinterpret
    for col in list(df.columns):
        if df[col].dtype in ['float64', 'int64'] and df[col].nunique() > 500:
            if col not in ("age", "income"):
                df = df.drop(columns=[col])

    # Recalculate after drops
    categorical = [c for c in df.columns if df[c].dtype == 'object' or df[c].dtype == 'bool']
    numerical = [c for c in df.columns if c not in categorical]

    print(f"  Columns: {len(categorical)} categorical, {len(numerical)} numerical")
    print(f"  Records: {len(df)}")

    trainer = ModelTrainer()
    trainer.fit(df, categorical_columns=categorical, numerical_columns=numerical)
    trainer.save(model_path)

    print(f"  Model saved to {model_path}")
    print()


def generate_profiles(model_path: str, registry_path: str, count: int = 50) -> list:
    """Generate the first batch of profiles."""
    print(f"Step 5: Generating {count} profiles...")

    gen = ProfileGenerator(model_path, registry_path)
    profiles = gen.generate_batch(count, batch_name="first-batch")

    print(f"\n  Generated {len(profiles)} profiles")
    if profiles:
        print(f"  Sample backstory:\n    {profiles[0].get('backstory', 'N/A')[:200]}...")
    print()
    return profiles


def print_summary(registry_path: str):
    """Print population summary."""
    with open(registry_path) as f:
        profiles = json.load(f)

    df = pd.DataFrame(profiles)
    print("=" * 60)
    print(f"POPULATION SUMMARY — {len(df)} profiles")
    print("=" * 60)

    for var in ["sex", "race", "education", "party_id", "religion_affiliation", "urban_rural", "state"]:
        if var in df.columns:
            dist = df[var].value_counts(normalize=True).round(3).to_dict()
            print(f"\n{var}:")
            for val, pct in sorted(dist.items(), key=lambda x: -x[1]):
                bar = "#" * int(pct * 40)
                print(f"  {val:25s} {pct:5.1%} {bar}")

    # Archetype distribution
    if "archetype_id" in df.columns:
        n_archetypes = df["archetype_id"].nunique()
        print(f"\nArchetypes: {n_archetypes}")

    print()


def main():
    data_dir = Path("data")
    raw_dir = data_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    model_path = str(data_dir / "models" / "first_batch.pkl")
    registry_path = str(data_dir / "profiles" / "registry.json")
    raw_cache = raw_dir / "acs_pums_sample.csv"

    # 1. Download or load cached PUMS data
    if raw_cache.exists():
        print(f"Using cached PUMS data from {raw_cache}")
        raw_df = pd.read_csv(raw_cache)
    else:
        raw_df = download_all_states()
        raw_df.to_csv(raw_cache, index=False)
        print(f"  Cached raw data to {raw_cache}")

    # 2. Harmonize
    harmonized = harmonize_pums(raw_df)

    # 3. Add synthetic political/social variables
    enriched = add_synthetic_political_vars(harmonized)

    # 4. Fit model
    fit_and_save_model(enriched, model_path)

    # 5. Generate first batch
    generate_profiles(model_path, registry_path, count=50)

    # 6. Summary
    print_summary(registry_path)

    print("Done! First batch generated successfully.")
    print(f"  Registry: {registry_path}")
    print(f"  Model: {model_path}")


if __name__ == "__main__":
    main()
