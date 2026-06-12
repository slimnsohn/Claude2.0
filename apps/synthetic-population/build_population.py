"""Build/rebuild the persona registry from CES data.

Usage: python build_population.py --target-n 5000 [--seed 42]

Backs up the existing registry, enforces the +-3% balance gate (exits 1
without writing on failure), rebuilds archetypes, writes registry +
data/profiles/build_report.json.
"""
import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from generator.archetypes import ArchetypeBuilder
from generator.population_builder import BalanceError, build_population


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target-n", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    batch_id = f"ces-balanced-v2-{args.target_n}"

    base = Path(__file__).parent
    ces_path = base / "data" / "raw" / "ces" / "ces_2024_common.csv"
    registry_path = base / "data" / "profiles" / "registry.json"

    if not ces_path.exists():
        print(f"CES data not found at {ces_path}")
        return 1

    try:
        profiles, report = build_population(str(ces_path), args.target_n, batch_id, args.seed)
    except BalanceError as e:
        print(f"ABORT: {e}\nRegistry NOT modified.")
        return 1

    # Archetypes
    df = pd.DataFrame(profiles)
    builder = ArchetypeBuilder(min_cell_size=3)
    df = builder.build(df)
    if list(df["profile_id"]) != [p["profile_id"] for p in profiles]:
        print("ABORT: archetype builder reordered rows; registry NOT modified.")
        return 1
    for i in range(len(profiles)):
        profiles[i]["archetype_id"] = df.iloc[i]["archetype_id"]

    # Backup then write
    if registry_path.exists():
        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        backup = registry_path.with_name(f"registry.rebuild-backup.{ts}.json")
        shutil.copy2(registry_path, backup)
        print(f"Backed up pre-rebuild registry to {backup.name}")

    registry_path.write_text(json.dumps(profiles, indent=2, default=str))
    (base / "data" / "profiles" / "build_report.json").write_text(
        json.dumps({"built_at": datetime.now().isoformat(), "target_n": args.target_n,
                    "seed": args.seed, "batch_id": batch_id,
                    "archetypes": int(df["archetype_id"].nunique()), **report}, indent=2))

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
