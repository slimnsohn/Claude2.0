"""Write data/execution_report.json from accumulated paper orders/fills."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pmtrader.backtest.execution_report import execution_report  # noqa: E402
from pmtrader.datalayer.store import Store  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    store = Store(ROOT / "data" / "pmtrader.db")
    try:
        report = execution_report(store)
    finally:
        store.close()
    out = ROOT / "data" / "execution_report.json"
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    print(f"\nreport -> {out}")


if __name__ == "__main__":
    main()
