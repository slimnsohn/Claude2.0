"""Reconstruct closed trades from the durable store.

Gate evidence must survive reboots, so the allocator's trade history is never
trusted in memory: this module rebuilds per-strategy closed-trade P&L from
fills + orders + resolutions on demand. FIFO lot matching; fees are included
in lot cost and netted from sale proceeds; market resolution settles
surviving lots at $1/$0. Paper vs live is classified by the run-scoped
"paper-" order-id prefix.
"""
from __future__ import annotations

from collections import defaultdict, deque

from pmtrader.core.models import Side
from pmtrader.datalayer.store import Store

PAPER_PREFIX = "paper-"


def closed_trades(store: Store) -> dict[str, dict[str, list[dict]]]:
    """Returns {"paper": {strategy: [{"ts","pnl"}]}, "live": {...}},
    each list ordered by exit timestamp."""
    orders = {o.id: o for o in store.all_orders()}
    token_condition: dict[str, str] = {}
    for m in store.all_markets():
        token_condition[m.token_id_yes] = m.condition_id
        token_condition[m.token_id_no] = m.condition_id
    resolutions = {r["condition_id"]: r for r in store.resolutions()}

    # (mode, strategy, token) -> FIFO deque of [size, cost, entry_ts]
    lots: dict[tuple, deque] = defaultdict(deque)
    out: dict[str, dict[str, list[dict]]] = {
        "paper": defaultdict(list), "live": defaultdict(list)}

    for f in store.fills():
        order = orders.get(f["order_id"])
        if order is None:
            continue  # fill without an order row: cannot attribute
        mode = "paper" if f["order_id"].startswith(PAPER_PREFIX) else "live"
        key = (mode, order.intent.strategy, f["token_id"])
        if f["side"] == Side.BUY.value:
            lots[key].append([f["size"], f["price"] * f["size"] + f["fee"],
                              f["ts"]])
            continue
        proceeds = f["price"] * f["size"] - f["fee"]
        remaining = f["size"]
        q = lots[key]
        while remaining > 1e-12 and q:
            lot = q[0]
            take = min(lot[0], remaining)
            cost_part = lot[1] * take / lot[0]
            pnl = proceeds * (take / f["size"]) - cost_part
            out[mode][order.intent.strategy].append({"ts": f["ts"], "pnl": pnl})
            lot[0] -= take
            lot[1] -= cost_part
            remaining -= take
            if lot[0] <= 1e-12:
                q.popleft()

    for (mode, strategy, token_id), q in lots.items():
        res = resolutions.get(token_condition.get(token_id, ""))
        if res is None:
            continue  # position still open: not a closed trade yet
        payout = 1.0 if res["winning_token_id"] == token_id else 0.0
        for size, cost, _entry_ts in q:
            out[mode][strategy].append(
                {"ts": res["resolved_ts"], "pnl": size * payout - cost})

    for mode in out:
        for strategy in out[mode]:
            out[mode][strategy].sort(key=lambda t: t["ts"])
    return {"paper": dict(out["paper"]), "live": dict(out["live"])}
