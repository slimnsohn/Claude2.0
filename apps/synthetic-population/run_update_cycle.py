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
