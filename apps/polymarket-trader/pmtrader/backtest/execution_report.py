"""Paper execution realism report.

Under backtest-first validation, paper trading exists to validate the
EXECUTION assumptions the backtest cost model makes — maker fill rates,
time-to-fill, taker price improvement — not to re-prove edge. These numbers
accumulate across reboots because they come straight from the store.
"""
from __future__ import annotations

import time

from pmtrader.datalayer.store import Store

PAPER_PREFIX = "paper-"
RESTING_STATUSES = {"OPEN", "CANCELLED", "EXPIRED"}


def execution_report(store: Store) -> dict:
    orders = [o for o in store.all_orders() if o.id.startswith(PAPER_PREFIX)]
    fills_by_order: dict[str, list[dict]] = {}
    for f in store.fills():
        fills_by_order.setdefault(f["order_id"], []).append(f)

    takers: list[tuple] = []   # (order, fills) that crossed immediately
    makers: list[tuple] = []   # (order, fills) that rested
    for o in orders:
        fs = fills_by_order.get(o.id, [])
        rested = (o.intent.post_only or any(f["maker"] for f in fs)
                  or (not fs and o.status.value in RESTING_STATUSES))
        (makers if rested else takers).append((o, fs))
    takers = [(o, fs) for o, fs in takers if fs]

    maker_filled = [(o, fs) for o, fs in makers if fs]
    secs = sorted(f["ts"] - o.created_ts for o, fs in maker_filled for f in fs)
    taker_fills = [(o, f) for o, fs in takers for f in fs]
    taker_shares = sum(f["size"] for _, f in taker_fills)

    def improvement(o, f) -> float:
        sign = 1.0 if f["side"] == "BUY" else -1.0
        return (o.intent.price - f["price"]) * sign * f["size"]

    return {
        "generated_ts": time.time(),
        "n_paper_orders": len(orders),
        "takers": {
            "n_orders": len(takers),
            "n_fills": len(taker_fills),
            "avg_fee_per_share": (sum(f["fee"] for _, f in taker_fills)
                                  / taker_shares) if taker_shares else 0.0,
            "avg_improvement_per_share": (sum(improvement(o, f)
                                              for o, f in taker_fills)
                                          / taker_shares) if taker_shares else 0.0,
        },
        "makers": {
            "n_resting_orders": len(makers),
            "n_filled": len(maker_filled),
            "fill_rate": len(maker_filled) / len(makers) if makers else 0.0,
            "median_secs_to_fill": secs[len(secs) // 2] if secs else None,
        },
    }
