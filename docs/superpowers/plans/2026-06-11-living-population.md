# Living Population Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scale the synthetic population to 5,000 balanced personas and replace flat party-level news shifts with a persistent, decaying, media-diet-filtered per-persona belief layer, guarded by a calibration gate, with update hooks (API/CLI/bat/UI) and a user guide page.

**Architecture:** Population is freshly resampled from 60K real CES 2024 respondents using raked weights (IPF) against census/CES marginals. News headlines are scored once per cycle (batched Haiku call, keyword fallback) into events with topic/direction/salience/per-outlet-family framing. Each persona probabilistically "sees" events through its `primary_news_source` outlet family and accumulates bounded (±0.15), decaying (14-day half-life) per-topic belief shifts that `engine/opinion.py` applies to KNN distributions at poll time. A calibration gate re-checks anchor benchmarks after every cycle and dampens drift on divergence.

**Tech Stack:** Python 3 / Flask / pandas / numpy / scikit-learn / pytest; vanilla JS frontend; Anthropic Messages API via `requests` (no new deps).

**Spec:** `docs/superpowers/specs/2026-06-11-living-population-design.md`

**Working directory for all commands:** `C:\Users\slims\Desktop\Claude 2.0\apps\synthetic-population`

**Run tests with:** `python -m pytest tests/ -v` (subset: `python -m pytest tests/test_X.py -v`)

**Commit policy:** the user has durably authorized checkpoint commits at task boundaries during long build sessions (memory: feedback_checkpoints). Commit at the end of each task; never push.

---

## File Structure

```
Create: generator/ces_harmonize.py        # shared CES→profile-field harmonization
Create: generator/population_builder.py   # raking, sampling, profile construction, balance report
Create: build_population.py               # CLI entry: --target-n, backup, gate, archetypes, write
Delete: build_balanced_population.py, expand_population.py, rebalance_population.py (after Task 3)
Create: engine/news_scoring.py            # keyword logic moved here + LLM batch scoring
Create: engine/news_fetch.py              # RSS fetch/sample helpers moved out of api/
Create: engine/registry_io.py             # atomic registry read/write with rotating backups
Create: engine/beliefs.py                 # belief state: decay, exposure, update, bounds, signs
Create: engine/update_cycle.py            # orchestrates fetch→score→decay→apply→persist→calibrate
Create: engine/calibration.py             # anchor re-check, stale detection, dampening
Modify: engine/opinion.py                 # apply per-persona belief shift (party shift = fallback)
Modify: api/world_updates.py              # import moved helpers; add /cycle + /belief-history routes
Modify: server.py                         # /guide route
Modify: static/index.html                 # nav link to /guide
Modify: static/app.js                     # Events tab: cycle button, calibration badge, drift chart
Create: static/guide.html                 # user guide + walkthroughs
Create: run_update_cycle.py, update.bat   # schedulable cycle hook
Create: tests/test_population_builder.py, tests/test_news_scoring.py, tests/test_beliefs.py,
        tests/test_calibration.py, tests/test_update_cycle.py
Modify: tests/test_opinion_engine.py      # belief-application tests
Data:   data/belief_history.json, data/calibration_history.json (new; legacy
        data/calibration_results.json is a dict from an old script — left untouched)
```

---

### Task 1: CES harmonization module + population builder core

**Files:**
- Create: `generator/ces_harmonize.py`
- Create: `generator/population_builder.py`
- Create: `tests/test_population_builder.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_population_builder.py
import random

import numpy as np
import pandas as pd
import pytest

from generator.ces_harmonize import harmonize_ces
from generator.population_builder import (
    CENSUS_TARGETS, KEY_VARS, compute_targets, rake_weights,
    respondent_to_profile, balance_report, BalanceError, check_balance,
)


def _fixture_ces(n=2000, seed=7):
    """Raw-format CES-like frame, deliberately skewed (too many strong_dem, too few strong_rep)."""
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "caseid": np.arange(1, n + 1),
        "pid7": rng.choice([1, 2, 3, 4, 5, 6, 7, 8], n, p=[.30, .12, .08, .15, .08, .10, .07, .10]),
        "gender4": rng.choice([1, 2, 3, 4], n, p=[.48, .48, .02, .02]),
        "race": rng.choice([1, 2, 3, 4, 5, 6, 7, 8], n, p=[.70, .08, .10, .04, .03, .02, .02, .01]),
        "educ": rng.choice([1, 2, 3, 4, 5, 6], n, p=[.05, .20, .15, .15, .28, .17]),
        "birthyr": rng.integers(1940, 2007, n),
        "urbancity": rng.choice([1, 2, 3, 4], n, p=[.30, .30, .15, .25]),
        "faminc_new": rng.integers(1, 17, n),
        "inputstate": rng.choice([6, 12, 36, 48], n),
        "ideo5": rng.choice([1, 2, 3, 4, 5], n),
        "CC24_410": rng.choice([1, 2, 3, 4], n),
        "religpew": rng.choice([1, 2, 9], n),
        "pew_bornagain": rng.choice([1, 2], n),
        "pew_churatd": rng.choice([1, 2, 3, 4, 5, 6], n),
    })


def test_harmonize_adds_profile_fields():
    df = harmonize_ces(_fixture_ces())
    for col in ["party_id", "sex", "race_h", "education", "age_bracket", "urban_rural"]:
        assert col in df.columns
    assert set(df["party_id"].dropna().unique()) <= {
        "strong_dem", "dem", "lean_dem", "independent", "lean_rep", "rep", "strong_rep"}
    assert str(df["age_bracket"].dtype) in ("object", "category")


def test_rake_weights_matches_marginals():
    df = harmonize_ces(_fixture_ces()).dropna(subset=KEY_VARS)
    targets = compute_targets(df)
    w = rake_weights(df, targets, KEY_VARS, iterations=30)
    assert w.shape[0] == len(df)
    assert abs(w.sum() - 1.0) < 1e-9
    # Weighted marginal for each var must be within 1% of target
    for var in KEY_VARS:
        dist = df.groupby(var, observed=True).apply(
            lambda g: w[g.index].sum(), include_groups=False)
        for val, tgt in targets[var].items():
            if val in dist.index:
                assert abs(dist[val] - tgt) < 0.01, f"{var}={val}"


def test_respondent_to_profile_fields():
    df = harmonize_ces(_fixture_ces())
    row = df.iloc[0]
    p = respondent_to_profile(row, batch_id="test-batch", rng=random.Random(1))
    assert p["ces_row_id"] == int(row["caseid"])
    assert p["batch_id"] == "test-batch"
    assert p["drift_log"] == []
    assert p["beliefs"] == {}
    assert p["party_id"] in {"strong_dem", "dem", "lean_dem", "independent",
                             "lean_rep", "rep", "strong_rep"}
    assert isinstance(p["income"], int)
    assert len(p["profile_id"]) == 8
    assert isinstance(p["backstory"], str) and len(p["backstory"]) > 20


def test_respondent_to_profile_deterministic_with_seed():
    df = harmonize_ces(_fixture_ces())
    row = df.iloc[3]
    a = respondent_to_profile(row, "b", rng=random.Random(42))
    b = respondent_to_profile(row, "b", rng=random.Random(42))
    a.pop("profile_id"); b.pop("profile_id")
    a.pop("created_at"); b.pop("created_at")
    a.pop("updated_at"); b.pop("updated_at")
    assert a == b


def test_balance_report_and_gate():
    profiles = [{"sex": "M", "race": "white", "education": "bachelors",
                 "age_bracket": "35-44", "party_id": "dem", "urban_rural": "urban"}] * 100
    targets = {"sex": {"M": 0.49, "F": 0.51}}
    report = balance_report(profiles, targets)
    assert report["max_gap"] > 0.03
    with pytest.raises(BalanceError):
        check_balance(report, tolerance=0.03)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_population_builder.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'generator.ces_harmonize'`

- [ ] **Step 3: Implement `generator/ces_harmonize.py`**

```python
"""Harmonize raw CES 2024 columns into profile-format fields.

Single source of truth for CES→profile mappings used by the population
builder (engine/ces_loader.py keeps its own copy tuned for KNN matching).
"""
import pandas as pd

CURRENT_YEAR = 2026

PARTY_MAP = {1: "strong_dem", 2: "dem", 3: "lean_dem", 4: "independent",
             5: "lean_rep", 6: "rep", 7: "strong_rep", 8: "independent"}
SEX_MAP = {1: "M", 2: "F", 3: "F", 4: "M"}
RACE_MAP = {1: "white", 2: "black", 3: "hispanic", 4: "asian",
            5: "other", 6: "multiracial", 7: "other", 8: "other"}
EDU_MAP = {1: "less_than_hs", 2: "hs_diploma", 3: "some_college",
           4: "some_college", 5: "bachelors", 6: "graduate"}
URBAN_MAP = {1: "urban", 2: "suburban", 3: "suburban", 4: "rural"}


def harmonize_ces(df: pd.DataFrame, current_year: int = CURRENT_YEAR) -> pd.DataFrame:
    out = df.copy()
    out["party_id"] = out["pid7"].map(PARTY_MAP)
    out["sex"] = out["gender4"].map(SEX_MAP)
    out["race_h"] = out["race"].map(RACE_MAP)
    out["education"] = out["educ"].map(EDU_MAP)
    age = current_year - out["birthyr"]
    out["age_bracket"] = pd.cut(
        age, bins=[0, 24, 34, 44, 54, 64, 200],
        labels=["18-24", "25-34", "35-44", "45-54", "55-64", "65+"],
    ).astype(str).replace("nan", None)
    out["urban_rural"] = out["urbancity"].map(URBAN_MAP)
    return out
```

- [ ] **Step 4: Implement `generator/population_builder.py`**

```python
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
    """Convert one harmonized CES row to a persona profile dict."""
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

    fix_profile(profile)
    profile["backstory"] = generate_backstory(profile)
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_population_builder.py -v`
Expected: 5 PASS. If `test_rake_weights_matches_marginals` fails on a sparse cell, increase fixture `n` to 4000 — do not loosen the assertion.

- [ ] **Step 6: Commit**

```bash
git add generator/ces_harmonize.py generator/population_builder.py tests/test_population_builder.py
git commit -m "feat(population): CES harmonization + raked population builder with balance gate"
```

---

### Task 2: Builder CLI, real 5,000-persona build, remove old scripts

**Files:**
- Create: `build_population.py`
- Delete: `build_balanced_population.py`, `expand_population.py`, `rebalance_population.py`

- [ ] **Step 1: Implement `build_population.py`**

```python
"""Build/rebuild the persona registry from CES data.

Usage: python build_population.py --target-n 5000 [--seed 42]

Backs up the existing registry, enforces the ±3% balance gate (exits 1
without writing on failure), rebuilds archetypes, writes registry +
data/profiles/build_report.json.
"""
import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from generator.population_builder import BalanceError, build_population

BATCH_ID = "ces-balanced-v2-5k"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target-n", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    base = Path(__file__).parent
    ces_path = base / "data" / "raw" / "ces" / "ces_2024_common.csv"
    registry_path = base / "data" / "profiles" / "registry.json"

    if not ces_path.exists():
        print(f"CES data not found at {ces_path}")
        return 1

    try:
        profiles, report = build_population(str(ces_path), args.target_n, BATCH_ID, args.seed)
    except BalanceError as e:
        print(f"ABORT: {e}\nRegistry NOT modified.")
        return 1

    # Archetypes
    import pandas as pd
    from generator.archetypes import ArchetypeBuilder
    df = pd.DataFrame(profiles)
    builder = ArchetypeBuilder(min_cell_size=3)
    df = builder.build(df)
    for i in range(len(profiles)):
        profiles[i]["archetype_id"] = df.iloc[i]["archetype_id"]

    # Backup then write
    if registry_path.exists():
        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        backup = registry_path.with_name(f"registry.backup.{ts}.json")
        shutil.copy2(registry_path, backup)
        print(f"Backed up old registry to {backup.name}")

    registry_path.write_text(json.dumps(profiles, indent=2, default=str))
    (base / "data" / "profiles" / "build_report.json").write_text(
        json.dumps({"built_at": datetime.now().isoformat(), "target_n": args.target_n,
                    "seed": args.seed, "batch_id": BATCH_ID,
                    "archetypes": df["archetype_id"].nunique(), **report}, indent=2))

    print(f"\nSaved {len(profiles)} profiles, {df['archetype_id'].nunique()} archetypes")
    print(f"Max marginal gap: {report['max_gap']:.1%}")
    for var, rows in report["vars"].items():
        print(f"\n{var}:")
        for val, r in rows.items():
            flag = "OK" if abs(r["gap"]) < 0.03 else f"{r['gap']:+.1%}"
            print(f"  {val:20s} {r['actual']:6.1%}  target={r['target']:6.1%}  {flag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run the real build**

Run: `python build_population.py --target-n 5000`
Expected: backup line, `Saved 5000 profiles, N archetypes`, `Max marginal gap` < 3%, all marginals `OK`. Takes a few minutes (180MB CSV + 5000 backstories). If the balance gate fails, inspect the printed report — likely a sparse `race_h=multiracial` or `education=less_than_hs` cell; raise raking iterations to 40 in `build_population` call before loosening anything.

- [ ] **Step 3: Sanity-check registry**

Run: `python -c "import json; ps=json.load(open('data/profiles/registry.json')); print(len(ps), ps[0]['batch_id'], 'ces_row_id' in ps[0], 'beliefs' in ps[0])"`
Expected: `5000 ces-balanced-v2-5k True True`

- [ ] **Step 4: Run full existing test suite (registry consumers must still pass)**

Run: `python -m pytest tests/ -v --timeout=300`  (drop `--timeout` if plugin absent)
Expected: all PASS. Investigate any failure before proceeding.

- [ ] **Step 5: Delete superseded one-off scripts and commit**

```bash
git rm --cached build_balanced_population.py expand_population.py rebalance_population.py 2>/dev/null
rm -f build_balanced_population.py expand_population.py rebalance_population.py
git add build_population.py data/profiles/build_report.json data/profiles/registry.json
git commit -m "feat(population): 5,000-persona balanced rebuild with provenance + balance gate"
```

(Note: `data/profiles/registry.json` is large; it is already tracked in this repo's data-in-git pattern. The `registry.backup.*.json` files stay untracked — add `data/profiles/registry.backup.*` to `.gitignore` if git status gets noisy.)

---

### Task 3: News scoring module (keyword move + LLM batch scoring)

**Files:**
- Create: `engine/news_scoring.py`
- Modify: `api/world_updates.py` (delete moved blocks, import from engine)
- Create: `tests/test_news_scoring.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_news_scoring.py
import json
from unittest.mock import patch, MagicMock

from engine.news_scoring import (
    detect_topics, detect_direction, compute_party_shift,
    score_events_keyword, score_events_llm, score_events, BELIEF_TOPICS,
)

HEADLINES = [
    {"title": "Inflation falls to 2.1% as economy beats expectations", "description": "", "feed": "AP"},
    {"title": "Border crossings surge to record high", "description": "", "feed": "BBC"},
]


def test_detect_topics_keyword():
    assert "economy" in detect_topics("inflation falls as economy improves")
    assert "immigration" in detect_topics("border crossings surge")
    assert detect_topics("local bake sale") == ["general"]


def test_keyword_scoring_shapes():
    events = score_events_keyword(HEADLINES)
    assert len(events) == 2
    e = events[0]
    assert e["scoring_method"] == "keyword"
    assert isinstance(e["direction"], float)
    assert 0.0 <= e["salience"] <= 1.0
    assert set(e["framing"].keys()) == {"right", "left", "mainstream"}
    # Keyword fallback: neutral framing (all families = 1.0)
    assert all(v == 1.0 for v in e["framing"].values())
    assert "economy" in e["topics"]


def _fake_llm_response(payload):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"content": [{"type": "text", "text": json.dumps(payload)}]}
    return resp


def test_llm_scoring_parses_and_clamps():
    payload = [
        {"topics": ["economy"], "direction": 0.8, "salience": 1.7,
         "framing": {"right": 0.4, "left": 1.0, "mainstream": 0.9}},
        {"topics": ["immigration", "bogus_topic"], "direction": -0.6, "salience": 0.9,
         "framing": {"right": 1.0, "left": -0.5, "mainstream": 0.7}},
    ]
    with patch("engine.news_scoring.requests.post", return_value=_fake_llm_response(payload)):
        events = score_events_llm(HEADLINES, api_key="test-key")
    assert events is not None and len(events) == 2
    assert events[0]["salience"] == 1.0          # clamped
    assert events[1]["topics"] == ["immigration"]  # unknown topic dropped
    assert events[0]["scoring_method"] == "llm"


def test_llm_scoring_malformed_returns_none():
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"content": [{"type": "text", "text": "not json"}]}
    with patch("engine.news_scoring.requests.post", return_value=resp):
        assert score_events_llm(HEADLINES, api_key="k") is None


def test_score_events_falls_back_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    events, method = score_events(HEADLINES)
    assert method == "keyword"
    assert len(events) == 2


def test_party_shift_unchanged_behavior():
    shifts = compute_party_shift(["economy"], "positive")
    assert shifts["rep"] > 0 and shifts["dem"] < 0  # incumbent = rep
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_news_scoring.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `engine/news_scoring.py`**

Move `TOPIC_KEYWORDS`, `POSITIVE_SIGNALS`, `NEGATIVE_SIGNALS`, `PARTY_VALENCE` verbatim from `api/world_updates.py:161-232`, and `_detect_topics` / `_detect_direction` / `_compute_opinion_shift` (renamed `detect_topics` / `detect_direction` / `compute_party_shift`). Then add:

```python
"""News scoring: keyword heuristics (moved from api/world_updates.py) + LLM batch scoring.

Event schema (one per headline):
  {text, description, feed, topics: [str], direction: float -1..1,
   salience: float 0..1, framing: {right,left,mainstream: float -1..1},
   scoring_method: "llm" | "keyword"}

Sign conventions (also stated in the LLM prompt):
  economy +: conditions good/improving      trump_approval +: favorable to administration
  immigration +: pro-enforcement mood       healthcare +: pro-public-program mood
  climate +: pro-climate-action mood        fiscal +: pro-progressive-tax mood
  education +: pro-debt-relief mood         crime/foreign_policy/social +: favors incumbent
"""
import json
import os
import re

import requests

BELIEF_TOPICS = ["economy", "trump_approval", "immigration", "healthcare", "climate",
                 "fiscal", "education", "crime", "foreign_policy", "social"]

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
SCORING_MODEL = "claude-haiku-4-5-20251001"

# ... moved constants and functions here (TOPIC_KEYWORDS, POSITIVE_SIGNALS,
# NEGATIVE_SIGNALS, PARTY_VALENCE, detect_topics, detect_direction,
# compute_party_shift) ...

# Map keyword-detector topic names to belief taxonomy (identical except extras)
_KEYWORD_TO_BELIEF = {t: t for t in BELIEF_TOPICS}
_KEYWORD_TO_BELIEF["gun_policy"] = "social"

_DIRECTION_VALUE = {"positive": 0.5, "negative": -0.5, "neutral": 0.0}


def score_events_keyword(headlines: list[dict]) -> list[dict]:
    events = []
    for h in headlines:
        text = (h.get("title", "") + " " + h.get("description", "")).strip()
        topics_raw = detect_topics(text)
        topics = sorted({_KEYWORD_TO_BELIEF.get(t) for t in topics_raw} - {None})
        direction_label = detect_direction(text)
        events.append({
            "text": h.get("title", ""),
            "description": h.get("description", ""),
            "feed": h.get("feed", ""),
            "topics": topics,
            "direction": _DIRECTION_VALUE[direction_label],
            "salience": 0.5,
            "framing": {"right": 1.0, "left": 1.0, "mainstream": 1.0},
            "scoring_method": "keyword",
        })
    return events


_LLM_SYSTEM = """You score news headlines for a public-opinion simulation. For each headline,
return an object: {"topics": [...], "direction": float, "salience": float,
"framing": {"right": float, "left": float, "mainstream": float}}.

topics: subset of """ + json.dumps(BELIEF_TOPICS) + """ (empty list if none apply).
direction (-1..1) sign conventions:
  economy: + = economic conditions good/improving
  trump_approval: + = favorable to the Trump administration
  immigration: + = strengthens pro-enforcement sentiment
  healthcare: + = strengthens support for public healthcare programs
  climate: + = strengthens support for climate action
  fiscal: + = strengthens support for taxing high incomes / opposing spending cuts
  education: + = strengthens support for student debt relief
  crime, foreign_policy, social: + = favorable to the incumbent administration
salience (0..1): how prominent/important the story is to the general public.
framing.X (-1..1): how X-leaning outlets spin it for their audience
(1 = amplify as-is, 0 = ignore, negative = spin to the opposite direction).

Return ONLY a JSON array, same length and order as the input. No prose."""


def score_events_llm(headlines: list[dict], api_key: str,
                     model: str = SCORING_MODEL, timeout: int = 60) -> list[dict] | None:
    """Batch-score headlines with one LLM call. Returns None on any failure (caller falls back)."""
    try:
        payload_in = [{"title": h.get("title", ""), "description": h.get("description", "")[:200]}
                      for h in headlines]
        resp = requests.post(
            ANTHROPIC_URL,
            timeout=timeout,
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": model, "max_tokens": 4000, "system": _LLM_SYSTEM,
                  "messages": [{"role": "user", "content": json.dumps(payload_in)}]},
        )
        if resp.status_code != 200:
            return None
        text = resp.json()["content"][0]["text"].strip()
        text = re.sub(r"^```(json)?|```$", "", text, flags=re.MULTILINE).strip()
        scored = json.loads(text)
        if not isinstance(scored, list) or len(scored) != len(headlines):
            return None

        def clamp(v, lo=-1.0, hi=1.0):
            return max(lo, min(hi, float(v)))

        events = []
        for h, s in zip(headlines, scored):
            topics = [t for t in s.get("topics", []) if t in BELIEF_TOPICS]
            framing = s.get("framing", {})
            events.append({
                "text": h.get("title", ""),
                "description": h.get("description", ""),
                "feed": h.get("feed", ""),
                "topics": topics,
                "direction": clamp(s.get("direction", 0.0)),
                "salience": clamp(s.get("salience", 0.5), 0.0, 1.0),
                "framing": {fam: clamp(framing.get(fam, 1.0)) for fam in ("right", "left", "mainstream")},
                "scoring_method": "llm",
            })
        return events
    except Exception:
        return None


def score_events(headlines: list[dict]) -> tuple[list[dict], str]:
    """LLM scoring when ANTHROPIC_API_KEY is set; keyword fallback otherwise."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if api_key:
        events = score_events_llm(headlines, api_key)
        if events is not None:
            return events, "llm"
    return score_events_keyword(headlines), "keyword"
```

- [ ] **Step 4: Update `api/world_updates.py` to import from the new module**

Delete lines 157–282 (the `TOPIC_KEYWORDS` block through `_compute_opinion_shift`) and add near the top:

```python
from engine.news_scoring import (
    TOPIC_KEYWORDS, POSITIVE_SIGNALS, NEGATIVE_SIGNALS, PARTY_VALENCE,
    detect_topics as _detect_topics,
    detect_direction as _detect_direction,
    compute_party_shift as _compute_opinion_shift,
)
```

(The `_sample_relevant` function at lines 112–154 references `TOPIC_KEYWORDS` etc. — leave it in place for now; it moves in Task 6.)

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_news_scoring.py tests/ -v`
Expected: new tests PASS, full suite still PASS (world_updates import path changed).

- [ ] **Step 6: Commit**

```bash
git add engine/news_scoring.py api/world_updates.py tests/test_news_scoring.py
git commit -m "feat(news): LLM batch headline scoring with keyword fallback; extract scoring module"
```

---

### Task 4: Registry IO + belief engine

**Files:**
- Create: `engine/registry_io.py`
- Create: `engine/beliefs.py`
- Create: `tests/test_beliefs.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_beliefs.py
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from engine.beliefs import (
    OUTLET_FAMILY, BELIEF_BOUND, HALF_LIFE_DAYS, CES_TOPIC_TO_BELIEF, BELIEF_SIGN,
    decay_factor, decay_beliefs, exposure_prob, susceptibility, apply_event,
    update_population,
)
from engine.registry_io import load_registry, save_registry

NOW = datetime(2026, 6, 11, 9, 0, 0)

EVENT = {
    "text": "Economy surges", "topics": ["economy"], "direction": 0.8,
    "salience": 1.0, "framing": {"right": 1.0, "left": 1.0, "mainstream": 1.0},
}


def _profile(**over):
    p = {"profile_id": "abc12345", "party_id": "independent",
         "primary_news_source": "local_tv", "beliefs": {}, "drift_log": []}
    p.update(over)
    return p


def test_decay_factor_half_life():
    assert decay_factor(0) == pytest.approx(1.0)
    assert decay_factor(HALF_LIFE_DAYS) == pytest.approx(0.5)
    assert decay_factor(2 * HALF_LIFE_DAYS) == pytest.approx(0.25)


def test_decay_beliefs_moves_toward_zero():
    p = _profile(beliefs={"economy": {"shift": 0.10, "exposures": 3,
                                      "last_updated": (NOW - timedelta(days=14)).isoformat()}})
    decay_beliefs(p, NOW)
    assert p["beliefs"]["economy"]["shift"] == pytest.approx(0.05)


def test_exposure_prob_bounds():
    assert exposure_prob(1.0, 1.0) == 1.0
    assert exposure_prob(0.4, 0.0) == pytest.approx(0.2)
    assert 0.0 <= exposure_prob(0.1, 0.3) <= 1.0


def test_susceptibility_confirmation_bias():
    # Positive economy news favors incumbent (rep): congenial for reps, counter for dems
    assert susceptibility("strong_dem", "economy", +1.0) == pytest.approx(0.7 * 0.4)
    assert susceptibility("strong_rep", "economy", +1.0) == pytest.approx(0.7)
    assert susceptibility("lean_dem", "economy", +1.0) == pytest.approx(0.4)
    assert susceptibility("independent", "economy", +1.0) == pytest.approx(1.0)


def test_apply_event_bounded_and_logged():
    import random
    p = _profile(party_id="rep", primary_news_source="fox_news",
                 beliefs={"economy": {"shift": 0.149, "exposures": 50,
                                      "last_updated": NOW.isoformat()}})
    rng = random.Random(0)  # exposure_prob = 1.0 for this event, always seen
    delta = apply_event(p, EVENT, NOW, rng, update_id="CY-TEST")
    assert p["beliefs"]["economy"]["shift"] <= BELIEF_BOUND
    assert p["drift_log"][-1]["update_id"] == "CY-TEST"
    assert p["drift_log"][-1]["topic"] == "economy"


def test_update_population_deterministic_and_summary():
    profiles = [_profile(profile_id=f"p{i:07d}", party_id="rep",
                         primary_news_source="fox_news") for i in range(20)]
    import copy
    profiles2 = copy.deepcopy(profiles)
    s1 = update_population(profiles, [EVENT], NOW, update_id="CY-1")
    s2 = update_population(profiles2, [EVENT], NOW, update_id="CY-1")
    assert profiles == profiles2          # same update_id → same exposures
    assert s1["exposures"] == s2["exposures"]
    assert "economy" in s1["mean_shift_by_topic"]
    assert s1["mean_shift_by_topic"]["economy"] > 0


def test_registry_io_atomic_backup(tmp_path):
    d = tmp_path / "data"
    (d / "profiles").mkdir(parents=True)
    (d / "profiles" / "registry.json").write_text(json.dumps([{"profile_id": "old"}]))
    save_registry(d, [{"profile_id": "new"}])
    assert load_registry(d)[0]["profile_id"] == "new"
    backups = list((d / "profiles").glob("registry.backup.*.json"))
    assert len(backups) == 1
    assert json.loads(backups[0].read_text())[0]["profile_id"] == "old"


def test_topic_and_sign_maps_cover_ces_columns():
    from engine.ces_columns import CES_COLUMNS
    for col_id, col in CES_COLUMNS.items():
        assert col["topic"] in CES_TOPIC_TO_BELIEF, col_id
        assert col_id in BELIEF_SIGN, col_id
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_beliefs.py -v`
Expected: FAIL — modules not found.

- [ ] **Step 3: Implement `engine/registry_io.py`**

```python
"""Atomic registry read/write with rotating timestamped backups (keep 3)."""
import json
import os
from datetime import datetime
from pathlib import Path

MAX_BACKUPS = 3


def _registry_path(data_dir) -> Path:
    return Path(data_dir) / "profiles" / "registry.json"


def load_registry(data_dir) -> list:
    p = _registry_path(data_dir)
    if not p.exists():
        return []
    return json.loads(p.read_text())


def save_registry(data_dir, profiles: list):
    p = _registry_path(data_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        ts = datetime.now().strftime("%Y%m%d%H%M%S%f")
        p.replace(p.with_name(f"registry.backup.{ts}.json"))
        backups = sorted(p.parent.glob("registry.backup.*.json"))
        for old in backups[:-MAX_BACKUPS]:
            old.unlink()
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(profiles, indent=2, default=str))
    os.replace(tmp, p)
```

(Note: `p.replace(backup)` moves the old file, then the tmp rename creates the new one — the registry is never half-written.)

- [ ] **Step 4: Implement `engine/beliefs.py`**

```python
"""Per-persona belief layer: media-diet exposure, bounded shifts, decay, audit trail.

Each profile carries:
  beliefs: {topic: {shift: float, exposures: int, last_updated: iso}}
Shift is a bounded (±BELIEF_BOUND) adjustment applied to the KNN yes-probability
of questions on that topic (sign per CES column via BELIEF_SIGN). Decays toward
zero (the CES-grounded baseline) with HALF_LIFE_DAYS.
"""
import random
from datetime import datetime

from engine.news_scoring import PARTY_VALENCE

BELIEF_BOUND = 0.15
BASE_RATE = 0.01
HALF_LIFE_DAYS = 14.0
DRIFT_LOG_MAX = 200
INCUMBENT = "rep"  # Trump administration 2025-2026
OPPOSITION = "dem"

OUTLET_FAMILY = {
    "fox_news": "right", "newsmax": "right", "oann": "right", "breitbart": "right",
    "msnbc": "left", "npr": "left", "new_york_times": "left",
    "washington_post": "left", "cnn": "left",
    "abc_news": "mainstream", "nbc_news": "mainstream", "cbs_news": "mainstream",
    "local_tv": "mainstream", "local_newspaper": "mainstream", "bbc": "mainstream",
    "the_hill": "mainstream", "politico": "mainstream",
}

# CES column topic → belief taxonomy topic
CES_TOPIC_TO_BELIEF = {
    "approval": "trump_approval", "economy": "economy", "immigration": "immigration",
    "healthcare": "healthcare", "environment": "climate", "fiscal": "fiscal",
    "education": "education",
}

# Per-CES-column sign: how a positive topic shift maps onto the column's yes-probability.
# Conventions documented in engine/news_scoring.py. 0 = beliefs don't apply.
BELIEF_SIGN = {
    "CC24_312i": +1, "CC24_311a": +1,                      # approval: + favors admin
    "CC24_301": +1, "CC24_302": +1, "CC24_303": +1,        # economy: + = doing well
    "CC24_300_1": +1, "CC24_300_3": +1, "CC24_300_4": +1,  # enforcement items
    "CC24_300_2": -1,                                      # DREAMers: pro-immigrant
    "CC24_326a": -1,                                       # repeal ACA vs pro-program mood
    "CC24_326b": +1, "CC24_326c": +1, "CC24_326d": +1, "CC24_326e": +1, "CC24_326f": +1,
    "CC24_415c": +1, "CC24_415d": +1, "CC24_308a_3": +1,   # climate action
    "CC24_308a_1": -1,                                     # cut spending vs progressive mood
    "CC24_308a_4": +1,                                     # tax >$400k
    "CC24_308a_2": 0,                                      # min wage: no clean mapping
    "CC24_308a_5": +1,                                     # student debt relief
}

_PARTY_GROUP = {
    "strong_dem": "dem", "dem": "dem", "lean_dem": "dem",
    "independent": "independent",
    "lean_rep": "rep", "rep": "rep", "strong_rep": "rep",
}
_STRONG = {"strong_dem", "strong_rep"}


def decay_factor(elapsed_days: float) -> float:
    return 0.5 ** (max(0.0, elapsed_days) / HALF_LIFE_DAYS)


def decay_beliefs(profile: dict, now: datetime):
    """Decay every topic shift toward zero based on elapsed time."""
    beliefs = profile.get("beliefs") or {}
    for topic, b in beliefs.items():
        try:
            last = datetime.fromisoformat(b.get("last_updated", now.isoformat()))
        except (TypeError, ValueError):
            last = now
        elapsed = (now - last).total_seconds() / 86400.0
        if elapsed > 0:
            b["shift"] = round(b["shift"] * decay_factor(elapsed), 6)
            b["last_updated"] = now.isoformat()


def exposure_prob(salience: float, framing_mag: float) -> float:
    return min(1.0, salience * (0.5 + 0.5 * abs(framing_mag)))


def _alignment(party_group: str, topic: str, effective_direction: float) -> str:
    """'congenial' | 'counter' | 'neutral' for this party on this signed event."""
    if party_group == "independent" or effective_direction == 0:
        return "neutral"
    valence = PARTY_VALENCE.get(topic, {})
    key = "positive" if effective_direction > 0 else "negative"
    beneficiary = valence.get(key, "mixed")
    if beneficiary == "incumbent":
        beneficiary = INCUMBENT
    elif beneficiary == "opposition":
        beneficiary = OPPOSITION
    if beneficiary == "mixed":
        return "neutral"
    return "congenial" if beneficiary == party_group else "counter"


def susceptibility(party_id: str, topic: str, effective_direction: float) -> float:
    group = _PARTY_GROUP.get(party_id, "independent")
    base = 0.7 if party_id in _STRONG else 1.0
    if _alignment(group, topic, effective_direction) == "counter":
        return base * 0.4
    return base


def apply_event(profile: dict, event: dict, now: datetime, rng: random.Random,
                update_id: str) -> float:
    """Maybe expose profile to event; update beliefs. Returns total |delta| applied."""
    family = OUTLET_FAMILY.get(profile.get("primary_news_source", ""), "mainstream")
    framing = (event.get("framing") or {}).get(family, 1.0)
    salience = float(event.get("salience", 0.5))
    direction = float(event.get("direction", 0.0))
    effective = direction * framing
    if not event.get("topics") or effective == 0.0:
        return 0.0
    if rng.random() >= exposure_prob(salience, framing):
        return 0.0

    beliefs = profile.setdefault("beliefs", {})
    drift_log = profile.setdefault("drift_log", [])
    total = 0.0
    for topic in event["topics"]:
        susc = susceptibility(profile.get("party_id", "independent"), topic, effective)
        delta = effective * salience * susc * BASE_RATE
        if delta == 0.0:
            continue
        b = beliefs.setdefault(topic, {"shift": 0.0, "exposures": 0,
                                       "last_updated": now.isoformat()})
        b["shift"] = round(max(-BELIEF_BOUND, min(BELIEF_BOUND, b["shift"] + delta)), 6)
        b["exposures"] = b.get("exposures", 0) + 1
        b["last_updated"] = now.isoformat()
        drift_log.append({"date": now.isoformat(), "topic": topic,
                          "delta": round(delta, 6), "update_id": update_id,
                          "shift_after": b["shift"]})
        total += abs(delta)
    if len(drift_log) > DRIFT_LOG_MAX:
        del drift_log[:-DRIFT_LOG_MAX]
    return total


def update_population(profiles: list, events: list, now: datetime,
                      update_id: str) -> dict:
    """Decay all profiles, then expose each to each event. Deterministic per update_id."""
    exposures = 0
    for p in profiles:
        # Reset corrupt beliefs defensively
        if not isinstance(p.get("beliefs"), dict):
            p["beliefs"] = {}
        decay_beliefs(p, now)
        rng = random.Random(f"{update_id}:{p.get('profile_id', '')}")
        for ev in events:
            if apply_event(p, ev, now, rng, update_id) > 0:
                exposures += 1

    # Aggregate summary
    sums, counts = {}, {}
    for p in profiles:
        for topic, b in (p.get("beliefs") or {}).items():
            sums[topic] = sums.get(topic, 0.0) + b.get("shift", 0.0)
            counts[topic] = counts.get(topic, 0) + 1
    n = max(1, len(profiles))
    return {
        "update_id": update_id,
        "date": now.isoformat(),
        "n_profiles": len(profiles),
        "n_events": len(events),
        "exposures": exposures,
        "mean_shift_by_topic": {t: round(s / n, 5) for t, s in sums.items()},
    }
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_beliefs.py -v`
Expected: all PASS. The `test_susceptibility_confirmation_bias` expectations encode: positive-economy news benefits the incumbent (rep) per `PARTY_VALENCE`.

- [ ] **Step 6: Commit**

```bash
git add engine/beliefs.py engine/registry_io.py tests/test_beliefs.py
git commit -m "feat(beliefs): per-persona belief layer with exposure, bounds, decay, audit trail"
```

---

### Task 5: Wire beliefs into the opinion engine

**Files:**
- Modify: `engine/opinion.py:129-141`
- Modify: `tests/test_opinion_engine.py` (append tests)

- [ ] **Step 1: Append failing tests to `tests/test_opinion_engine.py`**

Follow the file's existing fixture pattern for constructing the engine (it builds an `OpinionEngine` against a small fixture CSV — reuse that fixture). Append:

```python
def test_belief_shift_applied_per_persona(engine_fixture):
    """Personas with opposite economy beliefs diverge in their distributions."""
    base_profile = {"party_id": "independent", "education": "bachelors",
                    "age_bracket": "35-44", "race": "white", "urban_rural": "suburban"}
    up = {**base_profile, "beliefs": {"economy": {"shift": 0.10, "exposures": 5,
                                                  "last_updated": "2026-06-11T09:00:00"}}}
    down = {**base_profile, "beliefs": {"economy": {"shift": -0.10, "exposures": 5,
                                                    "last_updated": "2026-06-11T09:00:00"}}}
    q = "Is the economy getting better or worse?"
    d_up = engine_fixture.get_distribution(q, up)
    d_down = engine_fixture.get_distribution(q, down)
    d_base = engine_fixture.get_distribution(q, base_profile)
    assert d_up["yes"] > d_base["yes"] > d_down["yes"]


def test_belief_ignored_when_sign_zero(engine_fixture):
    """Min-wage column has BELIEF_SIGN 0 — beliefs must not move it."""
    base = {"party_id": "independent", "education": "bachelors",
            "age_bracket": "35-44", "race": "white", "urban_rural": "suburban"}
    bel = {**base, "beliefs": {"economy": {"shift": 0.15, "exposures": 9,
                                           "last_updated": "2026-06-11T09:00:00"}}}
    q = "Do you support raising the minimum wage to $15?"
    assert engine_fixture.get_distribution(q, bel)["yes"] == \
           engine_fixture.get_distribution(q, base)["yes"]


def test_party_shift_fallback_without_beliefs(engine_fixture):
    """Profiles lacking beliefs still respond to legacy world_shifts."""
    base = {"party_id": "rep", "education": "bachelors", "age_bracket": "35-44",
            "race": "white", "urban_rural": "suburban"}
    q = "Is the economy getting better or worse?"
    d_plain = engine_fixture.get_distribution(q, base)
    d_shift = engine_fixture.get_distribution(q, base, world_shifts={"rep": 0.05})
    assert d_shift["yes"] > d_plain["yes"]
```

(If the existing fixture is named differently, adapt the fixture name only — not the assertions. If the fixture CSV lacks `CC24_308a_2`, add that column to the fixture with values in {1,2}.)

- [ ] **Step 2: Run to verify the new tests fail**

Run: `python -m pytest tests/test_opinion_engine.py -v -k belief or fallback`
Expected: the two belief tests FAIL (beliefs not applied yet); fallback test may already pass.

- [ ] **Step 3: Implement in `engine/opinion.py`**

Add import at top:

```python
from engine.beliefs import BELIEF_SIGN, CES_TOPIC_TO_BELIEF
```

Replace the world-shift block (`# Apply world update shifts`, lines 129–141) with:

```python
        # Apply this persona's own belief shift (preferred), else legacy party shift
        applied_belief = False
        beliefs = profile.get("beliefs") or {}
        belief_topic = CES_TOPIC_TO_BELIEF.get(col_match.get("topic", ""))
        sign = BELIEF_SIGN.get(col_id, 0)
        if beliefs and belief_topic and sign != 0:
            shift = beliefs.get(belief_topic, {}).get("shift", 0.0)
            if shift:
                adj = sign * shift
                yes_p += adj
                no_p -= adj * 0.7
                unsure_p -= adj * 0.3
                applied_belief = True

        if not applied_belief and world_shifts:
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
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_opinion_engine.py tests/test_beliefs.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add engine/opinion.py tests/test_opinion_engine.py
git commit -m "feat(opinion): apply per-persona belief shifts with per-column signs; party shift as fallback"
```

---

### Task 6: Calibration gate

**Files:**
- Create: `engine/calibration.py`
- Create: `tests/test_calibration.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_calibration.py
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from engine.calibration import (
    MAE_THRESHOLD, STALE_DAYS, DAMPENING_FACTOR, ANCHOR_QUESTIONS,
    get_anchor_real_values, dampen_beliefs, evaluate_anchors, run_calibration,
)

NOW = datetime(2026, 6, 11, 9, 0, 0)


def _bench_file(tmp_path, date_str):
    d = tmp_path
    (d / "benchmarks.json").write_text(json.dumps([
        {"question": "Do you approve of Trump's job performance?",
         "real_results": {"yes": 0.46, "no": 0.50, "unsure": 0.04}, "date": date_str},
        {"question": "Is the economy getting better or worse?",
         "real_results": {"yes": 0.34, "no": 0.58, "unsure": 0.08}, "date": date_str},
    ]))
    return d


def test_anchor_loading_fresh(tmp_path):
    d = _bench_file(tmp_path, (NOW - timedelta(days=5)).strftime("%Y-%m-%d"))
    anchors = get_anchor_real_values(d, now=NOW)
    assert len(anchors) == 2
    assert not anchors[0]["stale"]


def test_anchor_stale_detection(tmp_path):
    d = _bench_file(tmp_path, (NOW - timedelta(days=45)).strftime("%Y-%m-%d"))
    anchors = get_anchor_real_values(d, now=NOW)
    assert all(a["stale"] for a in anchors)


def test_dampen_beliefs_halves_and_logs():
    profiles = [{"profile_id": "p1", "drift_log": [],
                 "beliefs": {"economy": {"shift": 0.10, "exposures": 4,
                                         "last_updated": NOW.isoformat()}}}]
    dampen_beliefs(profiles, DAMPENING_FACTOR, NOW, run_id="CY-X")
    assert profiles[0]["beliefs"]["economy"]["shift"] == pytest.approx(0.05)
    entry = profiles[0]["drift_log"][-1]
    assert entry["type"] == "calibration_dampening"
    assert entry["factor"] == DAMPENING_FACTOR


def test_run_calibration_verdicts(tmp_path):
    d = _bench_file(tmp_path, (NOW - timedelta(days=5)).strftime("%Y-%m-%d"))
    profiles = [{"profile_id": "p1", "drift_log": [], "beliefs": {}}]

    def good_poll(question, profs):
        return {"yes": 0.46, "no": 0.50, "unsure": 0.04}

    def bad_poll(question, profs):
        return {"yes": 0.70, "no": 0.27, "unsure": 0.03}

    res = run_calibration(d, profiles, poll_fn=good_poll, now=NOW, run_id="CY-1")
    assert res["verdict"] == "pass"

    res = run_calibration(d, profiles, poll_fn=bad_poll, now=NOW, run_id="CY-2")
    assert res["verdict"] == "drift_warning"
    assert res["dampened"] is True

    d2 = _bench_file(tmp_path / "stale", (NOW - timedelta(days=60)).strftime("%Y-%m-%d"))
    res = run_calibration(d2, profiles, poll_fn=bad_poll, now=NOW, run_id="CY-3")
    assert res["verdict"] == "stale"
    assert res["dampened"] is False


def test_history_appended(tmp_path):
    d = _bench_file(tmp_path, (NOW - timedelta(days=5)).strftime("%Y-%m-%d"))
    profiles = [{"profile_id": "p1", "drift_log": [], "beliefs": {}}]
    run_calibration(d, profiles, poll_fn=lambda q, p: {"yes": 0.46, "no": 0.50, "unsure": 0.04},
                    now=NOW, run_id="CY-1")
    hist = json.loads((d / "calibration_history.json").read_text())
    assert isinstance(hist, list) and hist[-1]["run_id"] == "CY-1"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_calibration.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `engine/calibration.py`**

```python
"""Calibration gate: re-check anchor benchmarks after belief updates.

Real anchor values come from data/benchmarks.json (manually refreshed by the
user — never scraped). Verdicts: pass | drift_warning (dampening applied) |
stale (real numbers >STALE_DAYS old; no pass/fail claim, no dampening).
History appends to data/calibration_history.json (the legacy
data/calibration_results.json single-run dict is left untouched).
"""
import json
from datetime import datetime
from pathlib import Path

MAE_THRESHOLD = 0.05
STALE_DAYS = 30
DAMPENING_FACTOR = 0.5
CALIBRATION_RUNS = 5

ANCHOR_QUESTIONS = [
    "Do you approve of Trump's job performance?",
    "Is the economy getting better or worse?",
]


def get_anchor_real_values(data_dir, now: datetime = None) -> list:
    """Find anchor questions in benchmarks.json (fallback: curated list)."""
    now = now or datetime.now()
    path = Path(data_dir) / "benchmarks.json"
    saved = json.loads(path.read_text()) if path.exists() else []
    try:
        from api.benchmarks import CURATED_BENCHMARKS
    except Exception:
        CURATED_BENCHMARKS = []

    anchors = []
    for q in ANCHOR_QUESTIONS:
        entry = next((b for b in saved if b.get("question", "").lower() == q.lower()), None)
        if entry is None:
            entry = next((b for b in CURATED_BENCHMARKS
                          if b["question"].lower() == q.lower()), None)
        if entry is None or not entry.get("real_results"):
            continue
        stale = True
        try:
            d = datetime.strptime(entry.get("date", ""), "%Y-%m-%d")
            stale = (now - d).days > STALE_DAYS
        except ValueError:
            pass
        anchors.append({"question": q, "real": entry["real_results"],
                        "date": entry.get("date", ""), "stale": stale})
    return anchors


def synthetic_distribution(question: str, profiles: list, engine,
                           runs: int = CALIBRATION_RUNS) -> dict:
    """Archetype-weighted distribution, averaged over runs. No Flask required."""
    import pandas as pd
    from generator.archetypes import ArchetypeBuilder

    df = pd.DataFrame(profiles)
    builder = ArchetypeBuilder(min_cell_size=1)
    df = builder.build(df)
    weights = builder.get_weights()
    reps = {}
    for rec in df.to_dict(orient="records"):
        aid = rec.get("archetype_id")
        if aid and aid not in reps:
            reps[aid] = rec

    totals = {"yes": 0.0, "no": 0.0, "unsure": 0.0}
    for _ in range(runs):
        yes_w = no_w = unsure_w = total_w = 0.0
        for aid, w in weights.items():
            result = engine.get_opinion(question, reps.get(aid, {}))
            if result is None:
                continue
            opinion, _, _ = result
            if opinion == "yes":
                yes_w += w
            elif opinion == "no":
                no_w += w
            else:
                unsure_w += w
            total_w += w
        if total_w > 0:
            totals["yes"] += yes_w / total_w
            totals["no"] += no_w / total_w
            totals["unsure"] += unsure_w / total_w
    return {k: round(v / runs, 4) for k, v in totals.items()}


def dampen_beliefs(profiles: list, factor: float, now: datetime, run_id: str):
    for p in profiles:
        beliefs = p.get("beliefs") or {}
        touched = False
        for b in beliefs.values():
            if b.get("shift"):
                b["shift"] = round(b["shift"] * factor, 6)
                touched = True
        if touched:
            p.setdefault("drift_log", []).append({
                "date": now.isoformat(), "type": "calibration_dampening",
                "factor": factor, "update_id": run_id,
            })


def evaluate_anchors(anchors: list, poll_fn, profiles: list) -> list:
    results = []
    for a in anchors:
        synth = poll_fn(a["question"], profiles)
        mae = sum(abs(synth.get(k, 0) - a["real"].get(k, 0))
                  for k in ("yes", "no", "unsure")) / 3.0
        results.append({**a, "synthetic": synth, "mae": round(mae, 4)})
    return results


def run_calibration(data_dir, profiles: list, poll_fn, now: datetime = None,
                    run_id: str = "") -> dict:
    """poll_fn(question, profiles) -> {yes,no,unsure}. Returns verdict + anchor detail."""
    now = now or datetime.now()
    anchors = get_anchor_real_values(data_dir, now=now)

    result = {"run_id": run_id, "date": now.isoformat(), "anchors": [],
              "verdict": "stale", "dampened": False}
    if not anchors:
        result["verdict"] = "stale"
        result["note"] = "no anchor benchmarks found"
    elif any(a["stale"] for a in anchors):
        result["anchors"] = evaluate_anchors(anchors, poll_fn, profiles)
        result["verdict"] = "stale"
    else:
        result["anchors"] = evaluate_anchors(anchors, poll_fn, profiles)
        if any(a["mae"] > MAE_THRESHOLD for a in result["anchors"]):
            dampen_beliefs(profiles, DAMPENING_FACTOR, now, run_id)
            result["dampened"] = True
            result["anchors_after"] = evaluate_anchors(anchors, poll_fn, profiles)
            result["verdict"] = "drift_warning"
        else:
            result["verdict"] = "pass"

    hist_path = Path(data_dir) / "calibration_history.json"
    history = json.loads(hist_path.read_text()) if hist_path.exists() else []
    history.append(result)
    hist_path.write_text(json.dumps(history[-100:], indent=2))
    return result
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_calibration.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add engine/calibration.py tests/test_calibration.py
git commit -m "feat(calibration): anchor re-check with stale detection and drift dampening"
```

---

### Task 7: Update cycle orchestrator + news fetch extraction

**Files:**
- Create: `engine/news_fetch.py` (move `_strip_html`, `_fetch_rss`, `_fetch_headlines`, `_sample_relevant`, `RSS_FEEDS`, `GOOGLE_NEWS_TOPICS` from `api/world_updates.py:38-154`)
- Create: `engine/update_cycle.py`
- Modify: `api/world_updates.py` (import moved fetch helpers)
- Create: `tests/test_update_cycle.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_update_cycle.py
import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

from engine.update_cycle import run_cycle

NOW = datetime(2026, 6, 11, 9, 0, 0)

HEADLINES = [
    {"title": "Inflation falls to 2.1 percent as economy beats expectations",
     "description": "Markets rally on strong jobs growth", "feed": "AP"},
    {"title": "Border crossings hit record high amid policy fight",
     "description": "", "feed": "BBC"},
]


def _setup_data(tmp_path):
    d = tmp_path / "data"
    (d / "profiles").mkdir(parents=True)
    profiles = [{
        "profile_id": f"p{i:07d}", "party_id": "rep" if i % 2 else "dem",
        "primary_news_source": "fox_news" if i % 2 else "msnbc",
        "education": "bachelors", "age_bracket": "35-44", "race": "white",
        "urban_rural": "suburban", "religion_attendance": "rarely",
        "beliefs": {}, "drift_log": [],
    } for i in range(10)]
    (d / "profiles" / "registry.json").write_text(json.dumps(profiles))
    (d / "benchmarks.json").write_text(json.dumps([
        {"question": "Do you approve of Trump's job performance?",
         "real_results": {"yes": 0.46, "no": 0.50, "unsure": 0.04},
         "date": (NOW - timedelta(days=3)).strftime("%Y-%m-%d")},
        {"question": "Is the economy getting better or worse?",
         "real_results": {"yes": 0.34, "no": 0.58, "unsure": 0.08},
         "date": (NOW - timedelta(days=3)).strftime("%Y-%m-%d")},
    ]))
    return d


def _fake_engine():
    eng = MagicMock()
    eng.get_opinion.return_value = ("yes", 6, "test")
    return eng


def test_run_cycle_full_pipeline(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    d = _setup_data(tmp_path)
    summary = run_cycle(d, _fake_engine(), fetch_fn=lambda: HEADLINES, now=NOW)

    assert summary["n_events"] == 2
    assert summary["scoring_method"] == "keyword"
    assert "calibration" in summary

    profiles = json.loads((d / "profiles" / "registry.json").read_text())
    assert any(p["beliefs"] for p in profiles)           # someone was exposed
    history = json.loads((d / "belief_history.json").read_text())
    assert history[-1]["update_id"] == summary["update_id"]
    updates = json.loads((d / "world_updates.json").read_text())
    assert all(u["source"] == "auto" for u in updates)
    assert all("shifts" in u for u in updates)            # legacy compat field


def test_run_cycle_no_headlines_still_decays(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    d = _setup_data(tmp_path)
    profiles = json.loads((d / "profiles" / "registry.json").read_text())
    profiles[0]["beliefs"] = {"economy": {"shift": 0.10, "exposures": 1,
                                          "last_updated": (NOW - timedelta(days=14)).isoformat()}}
    (d / "profiles" / "registry.json").write_text(json.dumps(profiles))

    summary = run_cycle(d, _fake_engine(), fetch_fn=lambda: [], now=NOW)
    assert summary["n_events"] == 0
    out = json.loads((d / "profiles" / "registry.json").read_text())
    assert abs(out[0]["beliefs"]["economy"]["shift"] - 0.05) < 1e-6
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_update_cycle.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Create `engine/news_fetch.py`**

Move `RSS_FEEDS`, `GOOGLE_NEWS_TOPICS`, `_strip_html`, `_fetch_rss`, `_fetch_headlines`, `_sample_relevant` from `api/world_updates.py` verbatim, renaming to public (`strip_html`, `fetch_rss`, `fetch_headlines`, `sample_relevant`). `sample_relevant` imports `TOPIC_KEYWORDS`, `POSITIVE_SIGNALS`, `NEGATIVE_SIGNALS` from `engine.news_scoring`. Then in `api/world_updates.py` delete the moved code and import:

```python
from engine.news_fetch import (
    RSS_FEEDS, fetch_headlines as _fetch_headlines,
    sample_relevant as _sample_relevant, strip_html as _strip_html,
)
```

- [ ] **Step 4: Implement `engine/update_cycle.py`**

```python
"""Full update cycle: fetch → score → decay → expose/update → persist → calibrate.

Flask-independent so both the API endpoint and the CLI can run it.
"""
import json
from datetime import datetime
from pathlib import Path

from engine.beliefs import update_population
from engine.calibration import run_calibration, synthetic_distribution
from engine.news_fetch import fetch_headlines, sample_relevant
from engine.news_scoring import compute_party_shift, score_events
from engine.registry_io import load_registry, save_registry

N_EVENTS_PER_CYCLE = 8


def _direction_label(direction: float) -> str:
    if direction > 0.1:
        return "positive"
    if direction < -0.1:
        return "negative"
    return "neutral"


def _events_to_updates(events: list, now: datetime, run_id: str) -> list:
    """World-updates entries: new scoring fields + legacy fields for UI/fallback compat."""
    updates = []
    for i, e in enumerate(events):
        label = _direction_label(e["direction"])
        updates.append({
            "id": f"WU-{now.strftime('%Y%m%d%H%M%S')}-{i:02d}",
            "text": e["text"],
            "description": e.get("description", ""),
            "date": now.strftime("%Y-%m-%d"),
            "created_at": now.isoformat(),
            "topics": e["topics"] or ["general"],
            "direction": label,
            "direction_score": e["direction"],
            "salience": e["salience"],
            "framing": e["framing"],
            "scoring_method": e["scoring_method"],
            "shifts": compute_party_shift(e["topics"] or ["general"], label),
            "active": True,
            "source": "auto",
            "feed": e.get("feed", ""),
            "cycle_id": run_id,
        })
    return updates


def run_cycle(data_dir, opinion_engine, fetch_fn=None, now: datetime = None) -> dict:
    data_dir = Path(data_dir)
    now = now or datetime.now()
    run_id = f"CY-{now.strftime('%Y%m%d%H%M%S')}"

    # 1. Fetch + sample headlines
    headlines = (fetch_fn or fetch_headlines)()
    sampled = sample_relevant(headlines, n=N_EVENTS_PER_CYCLE) if headlines else []

    # 2. Score
    events, method = score_events(sampled) if sampled else ([], "none")

    # 3. Persist world updates (replace previous auto entries, keep manual)
    wu_path = data_dir / "world_updates.json"
    existing = json.loads(wu_path.read_text()) if wu_path.exists() else []
    manual = [u for u in existing if u.get("source") != "auto"]
    wu_path.write_text(json.dumps(_events_to_updates(events, now, run_id) + manual, indent=2))

    # 4. Decay + apply to population
    profiles = load_registry(data_dir)
    summary = update_population(profiles, events, now, update_id=run_id)
    summary["scoring_method"] = method
    summary["headlines_scanned"] = len(headlines)

    # 5. Aggregate history row
    hist_path = data_dir / "belief_history.json"
    history = json.loads(hist_path.read_text()) if hist_path.exists() else []
    history.append({k: summary[k] for k in
                    ("update_id", "date", "n_events", "exposures", "mean_shift_by_topic")})
    hist_path.write_text(json.dumps(history[-365:], indent=2))

    # 6. Calibration gate (may dampen beliefs in place)
    if opinion_engine is not None and profiles:
        def poll_fn(question, profs):
            return synthetic_distribution(question, profs, opinion_engine)
        summary["calibration"] = run_calibration(
            data_dir, profiles, poll_fn, now=now, run_id=run_id)
    else:
        summary["calibration"] = {"verdict": "stale", "note": "no opinion engine"}

    # 7. Persist registry (post-decay, post-update, post-dampening)
    save_registry(data_dir, profiles)
    return summary
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_update_cycle.py tests/ -v`
Expected: new tests PASS; full suite PASS (world_updates fetch helpers now imported).

- [ ] **Step 6: Commit**

```bash
git add engine/news_fetch.py engine/update_cycle.py api/world_updates.py tests/test_update_cycle.py
git commit -m "feat(cycle): full update-cycle orchestrator (fetch, score, decay, apply, calibrate)"
```

---

### Task 8: API endpoint, CLI, update.bat

**Files:**
- Modify: `api/world_updates.py` (add routes)
- Create: `run_update_cycle.py`, `update.bat`

- [ ] **Step 1: Add routes to `api/world_updates.py`** (after the `clear_auto` route)

```python
@world_updates_bp.route("/api/world-updates/cycle", methods=["POST"])
def run_update_cycle():
    """Run the full update cycle: fetch → score → apply beliefs → calibrate."""
    from engine.update_cycle import run_cycle
    engine = current_app.config.get("OPINION_ENGINE")
    data_dir = Path(current_app.config["DATA_DIR"])
    try:
        summary = run_cycle(data_dir, engine)
    except Exception as e:
        return jsonify({"error": f"Cycle failed: {e}"}), 500
    return jsonify(summary)


@world_updates_bp.route("/api/world-updates/belief-history", methods=["GET"])
def belief_history():
    p = Path(current_app.config["DATA_DIR"]) / "belief_history.json"
    return jsonify(json.loads(p.read_text()) if p.exists() else [])


@world_updates_bp.route("/api/world-updates/calibration-status", methods=["GET"])
def calibration_status():
    p = Path(current_app.config["DATA_DIR"]) / "calibration_history.json"
    history = json.loads(p.read_text()) if p.exists() else []
    return jsonify(history[-1] if history else {"verdict": "none"})
```

- [ ] **Step 2: Create `run_update_cycle.py`**

```python
"""Run one belief update cycle from the command line (schedulable).

Usage: python run_update_cycle.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def main():
    base = Path(__file__).parent
    data_dir = base / "data"
    ces_path = data_dir / "raw" / "ces" / "ces_2024_common.csv"

    engine = None
    if ces_path.exists():
        from engine.opinion import OpinionEngine
        print("Loading CES data (may take a minute)...")
        engine = OpinionEngine(str(ces_path))

    from engine.update_cycle import run_cycle
    summary = run_cycle(data_dir, engine)

    print(json.dumps(summary, indent=2))
    verdict = summary.get("calibration", {}).get("verdict", "?")
    print(f"\nCycle {summary['update_id']}: {summary['n_events']} events "
          f"({summary['scoring_method']}), {summary['exposures']} exposures, "
          f"calibration: {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Create `update.bat`**

```bat
@echo off
cd /d "%~dp0"
echo Running population update cycle...
python run_update_cycle.py
if errorlevel 1 (
    echo Update cycle FAILED.
    pause
    exit /b 1
)
echo Done.
```

- [ ] **Step 4: Smoke-test endpoint registration**

Run: `python -c "from server import create_app; app = create_app(); rules = [str(r) for r in app.url_map.iter_rules()]; print([r for r in rules if 'cycle' in r or 'belief' in r or 'calibration' in r])"`
Expected: the three new routes listed.

- [ ] **Step 5: Commit**

```bash
git add api/world_updates.py run_update_cycle.py update.bat
git commit -m "feat(hooks): cycle endpoint, belief-history + calibration-status APIs, CLI + update.bat"
```

---

### Task 9: Events tab UI — cycle button, calibration badge, drift chart

**Files:**
- Modify: `static/app.js:1429-1450` (renderEventsView header card) and the wiring section after it

- [ ] **Step 1: Add UI elements to `renderEventsView`**

In the first card of `renderEventsView` (`static/app.js:1432-1449`), replace the button row div (lines 1435–1439) with:

```html
            <div style="display:flex;gap:8px;align-items:center;margin-bottom:8px;flex-wrap:wrap">
                <button id="wu-cycle" class="btn btn-primary">Run Update Cycle</button>
                <button id="wu-fetch" class="btn btn-sm">Refresh Headlines Only</button>
                <button id="wu-clear" class="btn btn-sm">Clear Auto</button>
                <span id="wu-calib-badge"></span>
                <span id="wu-status" style="font-size:12px;color:var(--text2)"></span>
            </div>
            <div id="wu-drift-chart" style="margin-bottom:8px"></div>
```

- [ ] **Step 2: Add handler + badge + chart functions**

Immediately after the existing `wu-fetch` click handler block (near `static/app.js:1560`), add:

```javascript
    document.getElementById("wu-cycle").addEventListener("click", async () => {
        const status = document.getElementById("wu-status");
        status.textContent = "Running update cycle (fetch → score → apply → calibrate)...";
        try {
            const s = await api("/api/world-updates/cycle", { method: "POST" });
            const verdict = (s.calibration && s.calibration.verdict) || "?";
            status.textContent = `Cycle ${s.update_id}: ${s.n_events} events (${s.scoring_method}), ` +
                `${s.exposures} exposures, calibration: ${verdict}`;
            loadWorldUpdates();
            loadCalibrationBadge();
            loadDriftChart();
        } catch (e) {
            status.textContent = `Cycle failed: ${e.message}`;
        }
    });

    async function loadCalibrationBadge() {
        const el = document.getElementById("wu-calib-badge");
        if (!el) return;
        try {
            const c = await api("/api/world-updates/calibration-status");
            const cls = { pass: "badge-live", drift_warning: "badge-warn", stale: "badge" };
            const label = { pass: "calibration: pass", drift_warning: "calibration: drift warning",
                            stale: "calibration: stale — refresh benchmarks", none: "calibration: never run" };
            el.innerHTML = `<span class="badge ${cls[c.verdict] || "badge"}">${label[c.verdict] || c.verdict}</span>`;
        } catch (e) { el.innerHTML = ""; }
    }

    async function loadDriftChart() {
        const el = document.getElementById("wu-drift-chart");
        if (!el) return;
        try {
            const hist = await api("/api/world-updates/belief-history");
            if (!hist.length) { el.innerHTML = ""; return; }
            const topics = [...new Set(hist.flatMap(h => Object.keys(h.mean_shift_by_topic || {})))];
            const latest = hist[hist.length - 1].mean_shift_by_topic || {};
            el.innerHTML = `<div class="section-title" style="font-size:12px">Population belief drift (mean shift, ${hist.length} cycles)</div>` +
                topics.map(t => {
                    const v = latest[t] || 0;
                    const w = Math.min(100, Math.abs(v) * 800);
                    const color = v >= 0 ? "var(--accent, #4a9eff)" : "#e06c5a";
                    return `<div style="display:flex;align-items:center;gap:6px;font-size:11px">
                        <span style="width:110px;color:var(--text2)">${esc(t)}</span>
                        <div style="width:${w}px;height:8px;background:${color};border-radius:2px"></div>
                        <span>${(v >= 0 ? "+" : "") + v.toFixed(4)}</span></div>`;
                }).join("");
        } catch (e) { el.innerHTML = ""; }
    }

    loadCalibrationBadge();
    loadDriftChart();
```

(If a `badge-warn` CSS class doesn't exist in `static/styles.css`, add `.badge-warn { background: #8a5a00; color: #ffd27d; }` next to the existing `.badge` rules.)

- [ ] **Step 3: Verify in browser**

Run: `start.bat`, open Events tab. Click **Run Update Cycle** (requires internet; with no `ANTHROPIC_API_KEY` it falls back to keyword scoring — both fine). Expected: status line reports events/exposures/verdict; badge renders; drift chart shows topic bars; Population view personas show non-empty `beliefs` (spot-check via `/api/profiles`).

- [ ] **Step 4: Commit**

```bash
git add static/app.js static/styles.css
git commit -m "feat(ui): run-cycle button, calibration badge, belief drift chart on Events tab"
```

---

### Task 10: User guide page

**Files:**
- Create: `static/guide.html`
- Modify: `server.py` (add `/guide` route after the `/` route)
- Modify: `static/index.html:22` (add nav link)

- [ ] **Step 1: Add the route in `server.py`** (after the `index` route)

```python
    @app.route("/guide")
    def guide():
        return app.send_static_file("guide.html")
```

- [ ] **Step 2: Add nav link in `static/index.html`** after the Data Sources link (line 22):

```html
            <a class="nav-link" href="/guide" style="margin-top:12px;border-top:1px solid var(--border,#333);padding-top:12px">📖 Guide</a>
```

- [ ] **Step 3: Create `static/guide.html`**

Standalone page, reuses `styles.css`, shared base CSS, and chat widget. Sticky TOC, anchored sections, live stats header that degrades gracefully. Full content (write all seven sections — the skeleton below shows structure and the complete live-stats script; flesh out each section's prose from the spec, `docs/superpowers/specs/2026-06-11-living-population-design.md` Section 6, keeping language plain and including the exact commands shown):

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Guide — Synthetic Population Engine</title>
<link rel="stylesheet" href="../../_shared/styles/base.css" onerror="">
<link rel="stylesheet" href="/static/styles.css">
<style>
  .guide-wrap { display: flex; gap: 32px; max-width: 1100px; margin: 0 auto; padding: 24px; }
  .guide-toc { position: sticky; top: 24px; align-self: flex-start; min-width: 220px;
               font-size: 13px; line-height: 2; }
  .guide-body { flex: 1; max-width: 760px; line-height: 1.65; }
  .guide-body h2 { margin-top: 40px; border-bottom: 1px solid var(--border, #333); padding-bottom: 6px; }
  .guide-body code, .guide-body pre { background: rgba(128,128,128,.12); border-radius: 4px; padding: 2px 6px; }
  .guide-body pre { padding: 12px; overflow-x: auto; }
  .stat-chip { display: inline-block; padding: 4px 10px; margin-right: 8px; border-radius: 12px;
               background: rgba(128,128,128,.15); font-size: 12px; }
  .arch-diagram { font-family: monospace; font-size: 12px; white-space: pre; background: rgba(128,128,128,.08);
                  padding: 16px; border-radius: 6px; overflow-x: auto; }
</style>
</head>
<body>
<div class="guide-wrap">
  <nav class="guide-toc">
    <strong>Guide</strong><br>
    <a href="#how-it-works">1. How it works</a><br>
    <a href="#run-a-poll">2. Run a poll</a><br>
    <a href="#update-population">3. Update the population</a><br>
    <a href="#increase-population">4. Increase the population</a><br>
    <a href="#calibration">5. Keep it calibrated</a><br>
    <a href="#other-operations">6. Other operations</a><br>
    <a href="#faq">7. FAQ &amp; limitations</a><br><br>
    <a href="/">&larr; Back to app</a>
  </nav>
  <main class="guide-body">
    <h1>Synthetic Population Engine — User Guide</h1>
    <div id="live-stats"><span class="stat-chip">server offline — static docs mode</span></div>

    <h2 id="how-it-works">1. How it works</h2>
    <!-- Plain-language explanation per spec Section 6.1: real CES respondents → balanced
         sampling (raking) → KNN opinion matching (50 nearest real respondents) →
         per-persona belief layer (media diet, bounds, decay) → calibration gate.
         Include this diagram: -->
    <div class="arch-diagram">
 CES 2024 (60,000 real survey respondents)
        │  raked sampling (census-balanced)
        ▼
 5,000 personas (registry.json) ──── archetypes (weighting)
        │                                   │
        │  KNN: 50 most similar real        │
        │  respondents per question         ▼
        ▼                              poll aggregation
 baseline opinion distribution ──► + persona belief shift ──► answer
        ▲                                   ▲
        │ decay toward baseline             │ bounded ±0.15/topic
        │                                   │
 update cycle: RSS headlines → LLM scoring → media-diet exposure
        │
        ▼
 calibration gate (vs real polls) → dampens drift if MAE &gt; 5%
    </div>
    <!-- ...prose... -->

    <h2 id="run-a-poll">2. Walkthrough: run a poll</h2>
    <!-- Steps per spec: Poll tab → type question → CES coverage indicator →
         blocked questions explained (no CES column = no guessing) → Results tab,
         breakdowns by party/race/age, confidence intervals. -->

    <h2 id="update-population">3. Walkthrough: update the population (news cycle)</h2>
    <!-- What a cycle does (fetch → score → expose via each persona's news source →
         bounded shifts → decay → calibrate). Run from Events tab button, or:
         <pre>update.bat</pre> Schedule daily via Windows Task Scheduler:
         Action = start a program, Program = full path to update.bat.
         Reading the drift chart and a persona's drift_log. -->

    <h2 id="increase-population">4. Walkthrough: increase the population</h2>
    <!-- <pre>python build_population.py --target-n 5000</pre>
         What the distribution report means; the ±3% balance gate (build aborts,
         registry untouched, on failure); backups at
         data/profiles/registry.backup.&lt;timestamp&gt;.json — restore by copying
         one back over registry.json. -->

    <h2 id="calibration">5. Walkthrough: keep it calibrated</h2>
    <!-- Refresh real numbers in the Benchmark tab (anchor questions: Trump approval,
         economy direction). Badge meanings: pass / drift warning (auto-dampened ×0.5)
         / stale (real numbers &gt;30 days old — refresh them; no pass/fail claimed). -->

    <h2 id="other-operations">6. Other operations</h2>
    <!-- Snapshots & backtesting, demographic poll filters, toggling individual world
         updates, data file map: registry.json, world_updates.json, belief_history.json,
         calibration_history.json, benchmarks.json, build_report.json. -->

    <h2 id="faq">7. FAQ &amp; limitations</h2>
    <!-- No abortion/gun-control coverage (CES 2024 data shape); why drift is bounded
         (personas evolve, don't become different people); real-data-only policy
         (no fabricated data, benchmarks are diagnostic not tuning targets). -->
  </main>
</div>
<script>
(async function () {
  try {
    const r = await fetch("/api/stats");
    if (!r.ok) return;
    const s = await r.json();
    let chips = "";
    if (s.profile_count !== undefined) chips += `<span class="stat-chip">${s.profile_count} personas</span>`;
    if (s.archetype_count !== undefined) chips += `<span class="stat-chip">${s.archetype_count} archetypes</span>`;
    const c = await fetch("/api/world-updates/calibration-status").then(x => x.ok ? x.json() : null).catch(() => null);
    if (c && c.verdict && c.verdict !== "none") chips += `<span class="stat-chip">calibration: ${c.verdict}</span>`;
    const h = await fetch("/api/world-updates/belief-history").then(x => x.ok ? x.json() : []).catch(() => []);
    if (h.length) chips += `<span class="stat-chip">last cycle: ${h[h.length - 1].date.slice(0, 10)}</span>`;
    if (chips) document.getElementById("live-stats").innerHTML = chips;
  } catch (e) { /* static mode */ }
})();
</script>
<script src="../../_skills/llm-chat-widget/dist/chat-widget.js"></script>
</body>
</html>
```

(Check `/api/stats` field names against `api/stats.py` before wiring chips; adapt keys if different. Write out the full prose for every commented section — no placeholder comments may remain in the shipped file.)

- [ ] **Step 4: Verify**

Run: `start.bat`, navigate to `http://localhost:5000/guide`. Expected: page renders with TOC, all 7 sections, live stat chips when server up. Open `static/guide.html` directly from disk: still readable (stats chip shows offline mode).

- [ ] **Step 5: Commit**

```bash
git add static/guide.html server.py static/index.html
git commit -m "feat(guide): user guide page with walkthroughs and live stats"
```

---

### Task 11: Full verification + real end-to-end cycle

- [ ] **Step 1: Full test suite**

Run: `python -m pytest tests/ -v`
Expected: all PASS (previously ~270 + ~30 new).

- [ ] **Step 2: Real update cycle**

Run: `python run_update_cycle.py`
Expected: loads CES, fetches real headlines, scores (`llm` if `ANTHROPIC_API_KEY` set, else `keyword`), exposures > 0, calibration verdict printed (likely `stale` if benchmark dates are >30 days old — that's correct behavior, note it). Registry timestamps updated; `data/belief_history.json` has one row.

- [ ] **Step 3: Benchmark sanity check**

Run a benchmark compare from the Benchmark tab (or `POST /api/benchmarks/compare`) for Trump approval. Expected: MAE comparable to pre-change (~2-4%) since fresh beliefs are tiny.

- [ ] **Step 4: Update project docs**

Add to `apps/synthetic-population/CLAUDE.md` under Quick Start: `update.bat — run one belief update cycle`. Keep file under 50 lines.

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat(living-population): complete belief layer, calibration gate, guide page"
```

---

## Self-Review Notes

- **Spec coverage:** Section 1 → Tasks 1–2; Section 2 → Task 3; Section 3 → Tasks 4–5; Section 4 → Tasks 7–9; Section 5 → Task 6 (wired in Task 7); Section 6 (guide) → Task 10; Section 7 (testing) → per-task tests + Task 11.
- **Known deviation:** calibration history goes to `data/calibration_history.json` (spec said `calibration_results.json`, but that file is an existing legacy dict from `calibration_test.py`; overwriting it would destroy real recorded results).
- **Type consistency:** `score_events` returns `(events, method)`; `run_cycle` consumes both. `update_population(profiles, events, now, update_id)` matches Task 4 signature. `run_calibration(data_dir, profiles, poll_fn, now, run_id)` matches Tasks 6–7 usage. `BELIEF_SIGN`/`CES_TOPIC_TO_BELIEF` live in `engine/beliefs.py`, imported by `engine/opinion.py`.
- **Archetype-representative note:** polls aggregate one representative per archetype; the representative's own `beliefs` field is what gets applied. With ~300–600 archetypes over 5,000 personas this approximates the population-level belief distribution; acceptable per spec.
