"""Empirical verification of the CES column registry against the raw CSV.

For every column in engine.ces_columns.CES_COLUMNS, prints:
  - raw value distribution
  - party (pid7) cross-tab of interpreted yes/no/unsure shares
and asserts the partisan direction matches the item's known polarity.

Run before shipping any registry change:
    python verify_ces_mappings.py
Exits 1 if any sanity check fails.
"""
import sys

import pandas as pd

from engine.ces_columns import CES_COLUMNS

CES_PATH = "data/raw/ces/ces_2024_common.csv"

# Direction sanity checks: (col_id, check_name, fn(shares) -> bool)
# shares = {party: {"yes": p, "no": p, "unsure": p}} of interpreted answers.
CHECKS = [
    ("CC24_410", "trump-vote share among reps > 80%",
     lambda s: s["rep"]["yes"] > 0.80),
    ("CC24_410", "trump-vote share among dems < 10%",
     lambda s: s["dem"]["yes"] < 0.10),
    ("CC24_312a", "dems approve Biden more than reps",
     lambda s: s["dem"]["yes"] > s["rep"]["yes"] + 0.3),
    ("CC24_312b", "Congress approval below 50% overall",
     lambda s: s["all"]["yes"] < 0.50),
    ("CC24_312i", "dems approve Harris more than reps",
     lambda s: s["dem"]["yes"] > s["rep"]["yes"] + 0.3),
    ("CC24_301", "dems say economy better > reps (Biden-era fielding)",
     lambda s: s["dem"]["yes"] > s["rep"]["yes"]),
    ("CC24_302", "dems report income gains > reps",
     lambda s: s["dem"]["yes"] > s["rep"]["yes"]),
    ("CC24_303", "everyone says prices increased (>75% overall)",
     lambda s: s["all"]["yes"] > 0.75),
    ("CC24_303", "reps say prices increased > dems",
     lambda s: s["rep"]["yes"] > s["dem"]["yes"]),
    ("CC24_323a", "dems support legal status > reps",
     lambda s: s["dem"]["yes"] > s["rep"]["yes"]),
    ("CC24_323b", "reps support border patrols > dems",
     lambda s: s["rep"]["yes"] > s["dem"]["yes"]),
    ("CC24_323c", "reps support wall > dems",
     lambda s: s["rep"]["yes"] > s["dem"]["yes"] + 0.3),
    ("CC24_323d", "dems support Dreamers > reps",
     lambda s: s["dem"]["yes"] > s["rep"]["yes"]),
    ("CC24_323f", "dems support student debt forgiveness > reps",
     lambda s: s["dem"]["yes"] > s["rep"]["yes"] + 0.3),
    ("CC24_328c", "reps support Medicaid work requirement > dems",
     lambda s: s["rep"]["yes"] > s["dem"]["yes"]),
    ("CC24_328d", "reps support ACA repeal > dems",
     lambda s: s["rep"]["yes"] > s["dem"]["yes"] + 0.3),
    ("CC24_328d", "ACA repeal ~35% overall (codebook: 21081/38895)",
     lambda s: 0.30 < s["all"]["yes"] < 0.40),
    ("CC24_328e", "dems support Medicaid expansion > reps",
     lambda s: s["dem"]["yes"] > s["rep"]["yes"]),
    ("CC24_326a", "dems support EPA CO2 regulation > reps",
     lambda s: s["dem"]["yes"] > s["rep"]["yes"] + 0.3),
    ("CC24_326b", "dems support renewables mandate > reps",
     lambda s: s["dem"]["yes"] > s["rep"]["yes"] + 0.3),
    ("CC24_326d", "reps support more fossil fuel production > dems",
     lambda s: s["rep"]["yes"] > s["dem"]["yes"] + 0.3),
    ("CC24_326e", "dems support halting federal leases > reps",
     lambda s: s["dem"]["yes"] > s["rep"]["yes"] + 0.3),
    ("CC24_321a", "dems support assault-rifle ban > reps",
     lambda s: s["dem"]["yes"] > s["rep"]["yes"] + 0.3),
    ("CC24_321b", "reps support easier concealed carry > dems",
     lambda s: s["rep"]["yes"] > s["dem"]["yes"] + 0.3),
    ("CC24_321c", "background checks bipartisan (>85% both parties)",
     lambda s: s["dem"]["yes"] > 0.85 and s["rep"]["yes"] > 0.85),
    ("CC24_324a", "dems support abortion-as-choice > reps",
     lambda s: s["dem"]["yes"] > s["rep"]["yes"] + 0.3),
    ("CC24_324c", "reps support total abortion ban > dems (both minority)",
     lambda s: s["rep"]["yes"] > s["dem"]["yes"] and s["all"]["yes"] < 0.25),
    ("CC24_324d", "dems support expanding abortion access > reps",
     lambda s: s["dem"]["yes"] > s["rep"]["yes"] + 0.3),
    ("CC24_308a_4", "dems select 'provide arms to Ukraine' > reps",
     lambda s: s["dem"]["yes"] > s["rep"]["yes"]),
    ("CC24_308a_1", "reps select 'do not get involved' > dems",
     lambda s: s["rep"]["yes"] > s["dem"]["yes"]),
]


def party_group(v):
    if v in (1, 2, 3):
        return "dem"
    if v in (5, 6, 7):
        return "rep"
    return "other"


def interpreted_shares(df, col_id, interpret):
    """{party: {yes,no,unsure}} shares of interpreted answers, NaN dropped."""
    sub = df[["party", col_id]].dropna(subset=[col_id])
    out = {}
    for grp, g in [("all", sub)] + list(sub.groupby("party")):
        interp = g[col_id].apply(interpret)
        counts = interp.value_counts()
        n = len(interp)
        out[grp] = {k: counts.get(k, 0) / n for k in ("yes", "no", "unsure")}
    return out


def main():
    cols = list(CES_COLUMNS.keys())
    df = pd.read_csv(CES_PATH, usecols=cols + ["pid7"], low_memory=False)
    print(f"Loaded {len(df)} rows from {CES_PATH}")
    df["party"] = df["pid7"].map(party_group)

    all_shares = {}
    for col_id, col in CES_COLUMNS.items():
        print(f"\n=== {col_id}  {col['name']}  [{col['topic']}] ===")
        raw = df[col_id].value_counts(dropna=False).sort_index()
        print("raw:", {(k if pd.notna(k) else "NaN"): int(v) for k, v in raw.items()})
        shares = interpreted_shares(df, col_id, col["interpret"])
        all_shares[col_id] = shares
        for grp in ("all", "dem", "rep"):
            s = shares[grp]
            print(f"  {grp:>5}: yes={s['yes']:.3f} no={s['no']:.3f} unsure={s['unsure']:.3f}")

    print("\n=== Direction sanity checks ===")
    failures = 0
    for col_id, name, fn in CHECKS:
        ok = fn(all_shares[col_id])
        print(f"  [{'PASS' if ok else 'FAIL'}] {col_id}: {name}")
        if not ok:
            failures += 1

    print(f"\n{len(CHECKS) - failures}/{len(CHECKS)} checks passed")
    if failures:
        print("VERIFICATION FAILED — do not ship this registry.")
        sys.exit(1)
    print("All mappings verified.")


if __name__ == "__main__":
    main()
