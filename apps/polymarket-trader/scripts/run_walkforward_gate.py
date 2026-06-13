"""Run the walk-forward backtest gate and write data/walkforward_report.json.

This is the primary edge evidence under backtest-first validation: strategies
that PASS here get the reduced paper gate (50 trades / 2 days, execution
validation only). S2 is excluded — microstructure cannot be replayed from
sampled mids. S3 is excluded — it needs the live spot feed; it keeps the
full 200-trade paper gate.

Usage:
    python scripts/run_walkforward_gate.py --folds 4
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pmtrader.backtest.costs import CostModel  # noqa: E402
from pmtrader.backtest.walkforward import run_walkforward  # noqa: E402
from pmtrader.datalayer.store import Store  # noqa: E402
from pmtrader.strategies.s1_arb import S1Arb  # noqa: E402
from pmtrader.strategies.s4_calib import S4Calib  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def factory() -> list:
    wl_path = ROOT / "config" / "strategies" / "s4_whitelist.json"
    whitelist = json.loads(wl_path.read_text()) if wl_path.exists() else []
    return [S1Arb(), S4Calib(whitelist=whitelist)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--folds", type=int, default=4)
    ap.add_argument("--half-spread", type=float, default=0.01)
    ap.add_argument("--slippage-bps", type=float, default=50.0)
    ap.add_argument("--book-depth", type=float, default=50.0)
    args = ap.parse_args()

    store = Store(ROOT / "data" / "pmtrader.db")
    try:
        report = run_walkforward(
            store, factory, k=args.folds,
            cost=CostModel(half_spread=args.half_spread,
                           slippage_bps=args.slippage_bps,
                           book_depth=args.book_depth))
    finally:
        store.close()

    out = ROOT / "data" / "walkforward_report.json"
    out.write_text(json.dumps(report, indent=2))
    print(f"report -> {out}")
    if "error" in report:
        print(f"ERROR: {report['error']}")
        return
    for name, r in report["strategies"].items():
        print(f"  {name:>10} n={r['n_trades']:>5} "
              f"ci=({r['pooled_ci'][0]:+.4f},{r['pooled_ci'][1]:+.4f}) "
              f"folds={r['fold_ns']} {'PASS' if r['pass'] else 'FAIL'}")


if __name__ == "__main__":
    main()
