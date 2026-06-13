"""CLI for pulling Polymarket historical data into the local store.

Usage:
    python scripts/fetch_history.py --resolved-since 2024-01-01 --max-markets 500
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pmtrader.datalayer.clob_rest import ClobRestClient  # noqa: E402
from pmtrader.datalayer.gamma import GammaClient  # noqa: E402
from pmtrader.datalayer.history import HistoryFetcher  # noqa: E402
from pmtrader.datalayer.store import Store  # noqa: E402

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "pmtrader.db"


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--resolved-since", default="2024-01-01")
    ap.add_argument("--max-markets", type=int, default=500)
    ap.add_argument("--fidelity", type=int, default=60, help="minutes per point")
    ap.add_argument("--rate", type=float, default=5.0, help="requests/sec")
    ap.add_argument("--no-active", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    store = Store(DB_PATH)
    gamma, clob = GammaClient(), ClobRestClient()
    fetcher = HistoryFetcher(store, gamma, clob, rate_limit_per_s=args.rate,
                             fidelity=args.fidelity)
    try:
        stats = await fetcher.run(resolved_since=args.resolved_since,
                                  max_markets=args.max_markets,
                                  include_active=not args.no_active)
        print(f"\nDone: {stats}")
    finally:
        await gamma.close()
        await clob.close()
        store.close()


if __name__ == "__main__":
    asyncio.run(main())
