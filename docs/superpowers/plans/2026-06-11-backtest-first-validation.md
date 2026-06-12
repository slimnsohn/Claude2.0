# Backtest-First Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make edge validation reboot-proof: walk-forward backtest becomes the primary promotion evidence, allocator gate evidence is rebuilt from SQLite on every startup, and the dead neg-risk arb path (the best-documented edge) is wired into the live loop.

**Architecture:** A new pure function reconstructs closed trades (FIFO lots, fees, resolution settlement) from the durable `fills`/`orders`/`resolutions` tables and hydrates the allocator on startup + every 10 min. A walk-forward harness splits stored price history into K time folds, replays fresh strategy instances per fold with finite synthetic book depth, and writes a PASS/FAIL report that lowers the paper-gate thresholds (200 trades/7 d → 50 trades/2 d) for strategies with backtest-proven edge. The orchestrator gains neg-risk event dispatch so S1's `on_event` actually runs.

**Tech Stack:** Python 3.11, pytest, SQLite (existing `pmtrader.datalayer.store.Store`), numpy (existing `backtest/stats.py`).

**Context for the implementer (read first):**
- Working dir: `C:\Users\slims\Desktop\Claude 2.0\apps\polymarket-trader`. Run tests with `.venv\Scripts\python -m pytest`.
- Paper order ids start with `paper-` (run-scoped, `pmtrader/execution/paper.py:59`); live ids don't. This is how reconstructed trades are classified paper vs live.
- The bug being fixed: `Allocator.record_paper_trades`/`record_trades` (`pmtrader/allocator.py:49-53`) are never called in production, so gates can never promote, and allocator state is in-memory only.
- Commits are allowed as checkpoints on this branch (`feat/polymarket-trader`) per user's standing checkpoint preference. Never push. End commit messages with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: Store helpers — `all_orders`, `last_decision_ts`, `price_history_span`

**Files:**
- Modify: `pmtrader/datalayer/store.py` (after `orders_by_status`, line ~206; after `decisions`, line ~265; after `tokens_with_history`, line ~172)
- Test: `tests/test_store.py` (append)

- [ ] **Step 1: Write the failing tests** — append to `tests/test_store.py`:

```python
class TestNewHelpers:
    def test_all_orders_roundtrip(self, store):
        from pmtrader.core.models import Intent, Order, OrderStatus, Side
        intent = Intent(strategy="s1_arb", token_id="tokA", side=Side.BUY,
                        price=0.5, size=10.0, expected_edge=0.01, reasoning="t")
        store.upsert_order(Order(id="paper-x-1", intent=intent,
                                 status=OrderStatus.FILLED,
                                 created_ts=1.0, updated_ts=2.0))
        orders = store.all_orders()
        assert len(orders) == 1 and orders[0].id == "paper-x-1"
        assert orders[0].intent.strategy == "s1_arb"

    def test_last_decision_ts(self, store):
        assert store.last_decision_ts("demotion", "s1_arb") is None
        store.insert_decision(100.0, "s1_arb", "demotion", {})
        store.insert_decision(200.0, "s1_arb", "demotion", {})
        store.insert_decision(300.0, "s2_mm", "demotion", {})
        assert store.last_decision_ts("demotion", "s1_arb") == 200.0

    def test_price_history_span(self, store):
        assert store.price_history_span() == (None, None)
        store.insert_price_history("tokA", [(10.0, 0.5), (30.0, 0.6)])
        store.insert_price_history("tokB", [(20.0, 0.4)])
        assert store.price_history_span() == (10.0, 30.0)
```

Note: `tests/test_store.py` already has a `store` fixture (`Store(tmp_path / ...)`); reuse it. If its fixture has a different name, match the existing name.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_store.py -k TestNewHelpers -v`
Expected: FAIL with `AttributeError: 'Store' object has no attribute 'all_orders'`

- [ ] **Step 3: Implement the three helpers** in `pmtrader/datalayer/store.py`. After `orders_by_status` add:

```python
    def all_orders(self) -> list[Order]:
        with self._lock:
            rows = self._conn.execute("SELECT payload FROM orders").fetchall()
        return [Order.model_validate_json(r["payload"]) for r in rows]
```

After `decisions` add:

```python
    def last_decision_ts(self, kind: str, strategy: str) -> Optional[float]:
        with self._lock:
            row = self._conn.execute(
                "SELECT MAX(ts) AS ts FROM decisions WHERE kind=? AND strategy=?",
                (kind, strategy)).fetchone()
        return row["ts"] if row and row["ts"] is not None else None
```

After `tokens_with_history` add:

```python
    def price_history_span(self) -> tuple[Optional[float], Optional[float]]:
        with self._lock:
            row = self._conn.execute(
                "SELECT MIN(ts) AS lo, MAX(ts) AS hi FROM price_history").fetchone()
        return (row["lo"], row["hi"])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/test_store.py -v`
Expected: all PASS (new and pre-existing)

- [ ] **Step 5: Commit**

```bash
git add pmtrader/datalayer/store.py tests/test_store.py
git commit -m "feat(pmtrader): store helpers for durable trade reconstruction"
```

---

### Task 2: Closed-trade reconstruction — `pmtrader/datalayer/trades.py`

**Files:**
- Create: `pmtrader/datalayer/trades.py`
- Test: `tests/test_trades.py` (new)

- [ ] **Step 1: Write the failing tests** — create `tests/test_trades.py`:

```python
"""closed_trades(): FIFO reconstruction of per-strategy P&L from the store."""
import pytest

from pmtrader.core.models import Fill, Intent, Market, Order, OrderStatus, Side
from pmtrader.datalayer.store import Store
from pmtrader.datalayer.trades import closed_trades


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "t.db")
    yield s
    s.close()


def put_order(store, order_id, strategy, token, side=Side.BUY, price=0.5):
    intent = Intent(strategy=strategy, token_id=token, side=side, price=price,
                    size=10.0, expected_edge=0.01, reasoning="t")
    store.upsert_order(Order(id=order_id, intent=intent,
                             status=OrderStatus.FILLED,
                             created_ts=1.0, updated_ts=2.0))


def put_fill(store, order_id, token, side, price, size, ts, fee=0.0):
    store.insert_fill(Fill(order_id=order_id, token_id=token, side=side,
                           price=price, size=size, fee=fee, ts=ts))


def put_market(store, cid="m1"):
    store.upsert_market(Market(condition_id=cid, question="Q?",
                               token_id_yes=f"{cid}-yes",
                               token_id_no=f"{cid}-no"))


class TestClosedTrades:
    def test_buy_then_sell_realizes_pnl_with_fees(self, store):
        put_order(store, "paper-a-1", "s1_arb", "tokA")
        put_fill(store, "paper-a-1", "tokA", Side.BUY, 0.40, 10.0, ts=100.0, fee=0.10)
        put_order(store, "paper-a-2", "s1_arb", "tokA", side=Side.SELL)
        put_fill(store, "paper-a-2", "tokA", Side.SELL, 0.60, 10.0, ts=200.0, fee=0.10)
        out = closed_trades(store)
        trades = out["paper"]["s1_arb"]
        assert len(trades) == 1
        # cost 4.0+0.10, proceeds 6.0-0.10 -> pnl 1.8
        assert trades[0]["pnl"] == pytest.approx(1.8)
        assert trades[0]["ts"] == 200.0

    def test_resolution_settles_open_lot(self, store):
        put_market(store, "m1")
        put_order(store, "paper-a-1", "s4_calib", "m1-yes")
        put_fill(store, "paper-a-1", "m1-yes", Side.BUY, 0.55, 20.0, ts=100.0)
        store.set_resolution("m1", winning_token_id="m1-yes", resolved_ts=900.0)
        out = closed_trades(store)
        trades = out["paper"]["s4_calib"]
        assert len(trades) == 1
        assert trades[0]["pnl"] == pytest.approx(20.0 - 11.0)  # payout - cost
        assert trades[0]["ts"] == 900.0

    def test_losing_resolution_pays_zero(self, store):
        put_market(store, "m1")
        put_order(store, "paper-a-1", "s4_calib", "m1-yes")
        put_fill(store, "paper-a-1", "m1-yes", Side.BUY, 0.55, 20.0, ts=100.0)
        store.set_resolution("m1", winning_token_id="m1-no", resolved_ts=900.0)
        out = closed_trades(store)
        assert out["paper"]["s4_calib"][0]["pnl"] == pytest.approx(-11.0)

    def test_unresolved_open_lot_is_not_a_trade(self, store):
        put_market(store, "m1")
        put_order(store, "paper-a-1", "s4_calib", "m1-yes")
        put_fill(store, "paper-a-1", "m1-yes", Side.BUY, 0.55, 20.0, ts=100.0)
        out = closed_trades(store)
        assert out["paper"] == {}

    def test_partial_sell_fifo(self, store):
        put_order(store, "paper-a-1", "s1_arb", "tokA")
        put_fill(store, "paper-a-1", "tokA", Side.BUY, 0.40, 10.0, ts=100.0)
        put_fill(store, "paper-a-1", "tokA", Side.BUY, 0.50, 10.0, ts=110.0)
        put_order(store, "paper-a-2", "s1_arb", "tokA", side=Side.SELL)
        put_fill(store, "paper-a-2", "tokA", Side.SELL, 0.60, 15.0, ts=200.0)
        out = closed_trades(store)
        trades = out["paper"]["s1_arb"]
        # first lot (10 @ .40) fully closed, second lot 5 of 10 @ .50 closed
        assert len(trades) == 2
        assert sum(t["pnl"] for t in trades) == pytest.approx(
            (0.60 - 0.40) * 10 + (0.60 - 0.50) * 5)

    def test_live_and_paper_split_by_order_id_prefix(self, store):
        put_order(store, "paper-a-1", "s1_arb", "tokA")
        put_fill(store, "paper-a-1", "tokA", Side.BUY, 0.4, 5.0, ts=1.0)
        put_order(store, "0xlive1", "s1_arb", "tokB")
        put_fill(store, "0xlive1", "tokB", Side.BUY, 0.4, 5.0, ts=1.0)
        put_order(store, "paper-a-2", "s1_arb", "tokA", side=Side.SELL)
        put_fill(store, "paper-a-2", "tokA", Side.SELL, 0.5, 5.0, ts=2.0)
        put_order(store, "0xlive2", "s1_arb", "tokB", side=Side.SELL)
        put_fill(store, "0xlive2", "tokB", Side.SELL, 0.5, 5.0, ts=2.0)
        out = closed_trades(store)
        assert len(out["paper"]["s1_arb"]) == 1
        assert len(out["live"]["s1_arb"]) == 1

    def test_orphan_fill_without_order_is_skipped(self, store):
        put_fill(store, "ghost-1", "tokA", Side.BUY, 0.4, 5.0, ts=1.0)
        assert closed_trades(store) == {"paper": {}, "live": {}}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_trades.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pmtrader.datalayer.trades'`

- [ ] **Step 3: Create `pmtrader/datalayer/trades.py`:**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/test_trades.py -v`
Expected: 7 PASS

- [ ] **Step 5: Commit**

```bash
git add pmtrader/datalayer/trades.py tests/test_trades.py
git commit -m "feat(pmtrader): FIFO closed-trade reconstruction from the store"
```

---

### Task 3: Allocator — hydration + backtest-aware gate

**Files:**
- Modify: `pmtrader/allocator.py`
- Test: `tests/test_allocator.py` (append)

- [ ] **Step 1: Write the failing tests** — append to `tests/test_allocator.py` (it already imports `Allocator`, `GateStatus` and has a `trades(...)` helper at the top; reuse it — it builds a list of `{"ts","pnl"}` dicts):

```python
class TestHydrationAndBacktestGate:
    def test_hydrate_replaces_history(self):
        a = Allocator(["s1"], 1000.0)
        a.record_paper_trades("s1", trades(+1.0, 5, alt=0.1))
        a.hydrate(paper={"s1": trades(+0.5, 3, alt=0.1)}, live={})
        assert len(a.paper_trades["s1"]) == 3
        assert a.live_trades["s1"] == []

    def test_hydrate_ignores_unknown_strategies(self):
        a = Allocator(["s1"], 1000.0)
        a.hydrate(paper={"sX": trades(+0.5, 3, alt=0.1)}, live={})
        assert "sX" not in a.paper_trades or a.paper_trades["sX"] == []

    def test_backtest_pass_lowers_gate_thresholds(self):
        a = Allocator(["s1"], 1000.0)
        a.set_backtest_pass({"s1": True})
        # 60 trades over 3 days: passes only the reduced gate
        a.record_paper_trades("s1", trades(+0.5, 60, alt=0.2,
                                           start_ts=0.0, spacing=4320.0))
        a.update_gates(now=60 * 4320.0)
        assert a.gate("s1") == GateStatus.LIVE_ELIGIBLE

    def test_without_backtest_pass_full_gate_applies(self):
        a = Allocator(["s1"], 1000.0)
        a.record_paper_trades("s1", trades(+0.5, 60, alt=0.2,
                                           start_ts=0.0, spacing=4320.0))
        a.update_gates(now=60 * 4320.0)
        assert a.gate("s1") == GateStatus.PAPER

    def test_backtest_fail_keeps_full_gate(self):
        a = Allocator(["s1"], 1000.0)
        a.set_backtest_pass({"s1": False})
        a.record_paper_trades("s1", trades(+0.5, 60, alt=0.2,
                                           start_ts=0.0, spacing=4320.0))
        a.update_gates(now=60 * 4320.0)
        assert a.gate("s1") == GateStatus.PAPER
```

Note: check the existing `trades()` helper signature at the top of `tests/test_allocator.py` — if it doesn't accept `start_ts`/`spacing` kwargs, adapt the calls to however it spreads timestamps (the existing gate tests at lines ~71-97 spread trades over ≥7 days; copy that pattern but compress to ~3 days, i.e. spacing such that `(now - first_ts)/86400 >= 2` and `< 7`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_allocator.py -k Hydration -v`
Expected: FAIL with `AttributeError: 'Allocator' object has no attribute 'hydrate'`

- [ ] **Step 3: Implement.** In `pmtrader/allocator.py`:

Add class constants after `GATE_MIN_DAYS = 7.0` (line 32):

```python
    # reduced gate for strategies whose edge already passed the walk-forward
    # backtest: paper then only validates execution, not edge
    BT_GATE_MIN_TRADES = 50
    BT_GATE_MIN_DAYS = 2.0
```

In `__init__` (after `self.events: list[dict] = []`):

```python
        self.backtest_pass: dict[str, bool] = {}
```

After `record_paper_trades` add:

```python
    def hydrate(self, paper: dict[str, list[dict]],
                live: dict[str, list[dict]]) -> None:
        """Replace trade history from the durable store (reboot-safe)."""
        for s in self.strategies:
            self.paper_trades[s] = list(paper.get(s, []))
            self.live_trades[s] = list(live.get(s, []))

    def set_backtest_pass(self, passes: dict[str, bool]) -> None:
        self.backtest_pass = dict(passes)
```

Replace `_passes_paper_gate` (lines 135-143) with:

```python
    def _gate_thresholds(self, strategy: str) -> tuple[int, float]:
        if self.backtest_pass.get(strategy):
            return self.BT_GATE_MIN_TRADES, self.BT_GATE_MIN_DAYS
        return self.GATE_MIN_TRADES, self.GATE_MIN_DAYS

    def _passes_paper_gate(self, strategy: str, now: float) -> bool:
        trades = self.paper_trades[strategy]
        min_trades, min_days = self._gate_thresholds(strategy)
        if len(trades) < min_trades:
            return False
        span_days = (now - min(t["ts"] for t in trades)) / DAY
        if span_days < min_days:
            return False
        lo, _hi = bootstrap_ci([t["pnl"] for t in trades])
        return lo > 0
```

Also update the module docstring's gate description (lines 7-12) to mention the reduced backtest-backed gate.

- [ ] **Step 4: Run the full allocator suite**

Run: `.venv\Scripts\python -m pytest tests/test_allocator.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add pmtrader/allocator.py tests/test_allocator.py
git commit -m "feat(pmtrader): allocator hydration + backtest-aware gate thresholds"
```

---

### Task 4: Orchestrator — durable gate evidence, persisted reweight clock, persisted allocator events

**Files:**
- Modify: `pmtrader/orchestrator.py`
- Test: `tests/test_orchestrator.py` (append)

- [ ] **Step 1: Write the failing tests** — append to `tests/test_orchestrator.py` (reuse its `store`/`orch` fixtures and `mk_market`):

```python
class TestDurableAllocatorEvidence:
    def test_refresh_hydrates_paper_trades_from_store(self, orch, store):
        plant_arb(orch)  # produces 2 BUY fills via paper backend
        store.set_resolution("m1", winning_token_id="m1-yes", resolved_ts=500.0)
        orch.refresh_allocator_trades()
        trades = orch.allocator.paper_trades["s1_arb"]
        assert len(trades) == 2  # yes leg (won) + no leg (lost)
        assert sum(t["pnl"] for t in trades) > 0  # arb locked > 0 net

    def test_refresh_respects_demotion_cutoff(self, orch, store):
        plant_arb(orch)
        store.set_resolution("m1", winning_token_id="m1-yes", resolved_ts=500.0)
        store.insert_decision(600.0, "s1_arb", "demotion", {})
        orch.refresh_allocator_trades()
        assert orch.allocator.paper_trades["s1_arb"] == []

    def test_allocator_events_flushed_to_store(self, orch, store):
        orch.allocator.events.append(
            {"kind": "promotion", "ts": 1.0, "strategy": "s1_arb",
             "evidence": "test"})
        orch.flush_allocator_events()
        rows = [d for d in store.decisions(limit=10)
                if d["kind"] == "promotion"]
        assert len(rows) == 1 and rows[0]["strategy"] == "s1_arb"
        orch.flush_allocator_events()  # idempotent: no duplicate rows
        assert len([d for d in store.decisions(limit=10)
                    if d["kind"] == "promotion"]) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_orchestrator.py -k Durable -v`
Expected: FAIL with `AttributeError: ... 'refresh_allocator_trades'`

- [ ] **Step 3: Implement.** In `pmtrader/orchestrator.py`:

Add import at the top (with the other pmtrader imports):

```python
from pmtrader.datalayer.trades import closed_trades
```

In `__init__`, after `self._strategy_errors: dict[str, int] = {}` add:

```python
        self._alloc_events_flushed = 0
```

Add two methods after `startup_reconcile` (line ~226):

```python
    def refresh_allocator_trades(self) -> None:
        """Rebuild gate evidence from the durable store. Reboot-safe: the
        in-memory allocator never accumulates state the DB doesn't hold.
        Trades from before a strategy's last demotion don't count toward
        re-promotion (fresh-record rule)."""
        trades = closed_trades(self.store)
        paper, live = dict(trades["paper"]), dict(trades["live"])
        for s in self.allocator.strategies:
            cutoff = self.store.last_decision_ts("demotion", s)
            if cutoff is not None:
                paper[s] = [t for t in paper.get(s, []) if t["ts"] > cutoff]
        self.allocator.hydrate(paper, live)

    def flush_allocator_events(self) -> None:
        events = self.allocator.events
        for ev in events[self._alloc_events_flushed:]:
            self.store.insert_decision(
                ev.get("ts", time.time()), ev.get("strategy", "allocator"),
                ev["kind"], ev)
        self._alloc_events_flushed = len(events)
```

In `run()` (line ~317), after `self.startup_reconcile(time.time())` add:

```python
        self.refresh_allocator_trades()
```

Replace the timer initialization (line 328):

```python
        last_refresh = last_spot = last_resolution = time.time()
        ckpt = self.store.get_checkpoint("last_reweight")
        last_reweight = float(ckpt) if ckpt else time.time()
        if ckpt is None:
            self.store.set_checkpoint("last_reweight", str(last_reweight))
```

In the loop, after `self.allocator.update_gates(now)` add:

```python
                self.flush_allocator_events()
```

In the resolution branch (after `await self.check_resolutions()`), add:

```python
                    self.refresh_allocator_trades()
```

Replace the reweight branch:

```python
                if now - last_reweight > 7 * 86_400:
                    self.allocator.reweight(now)
                    last_reweight = now
                    self.store.set_checkpoint("last_reweight", str(now))
                    self.flush_allocator_events()
```

- [ ] **Step 4: Run tests**

Run: `.venv\Scripts\python -m pytest tests/test_orchestrator.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add pmtrader/orchestrator.py tests/test_orchestrator.py
git commit -m "feat(pmtrader): reboot-proof gate evidence + persisted reweight clock"
```

---

### Task 5: Wire neg-risk event dispatch (S1's best edge, currently dead)

**Files:**
- Modify: `pmtrader/orchestrator.py` (`refresh_markets` line ~277, `on_book` line ~171)
- Test: `tests/test_orchestrator.py` (append)

- [ ] **Step 1: Write the failing tests** — append to `tests/test_orchestrator.py`:

```python
import asyncio

from pmtrader.datalayer.gamma import Event


def mk_negrisk_event(n=3):
    markets = [mk_market(cid=f"e{i}") for i in range(n)]
    for m in markets:
        m.event_id = "ev9"
    return Event(id="ev9", title="who wins?", neg_risk=True, markets=markets)


class TestNegRiskDispatch:
    def test_on_book_dispatches_on_event_for_negrisk(self, orch, store):
        ev = mk_negrisk_event()
        orch.events["ev9"] = ev
        for m in ev.markets:
            orch.register_market(m)
        # all three YES asks sum to 0.90 -> set arb
        for m in ev.markets[:-1]:
            orch.on_book(mk_book(m.token_id_yes, 0.28, 0.30))
        orch.on_book(mk_book(ev.markets[-1].token_id_yes, 0.28, 0.30))
        fills = store.fills()
        yes_tokens = {m.token_id_yes for m in ev.markets}
        assert yes_tokens <= {f["token_id"] for f in fills}

    def test_refresh_markets_tracks_overlapping_negrisk_events(self, orch):
        ev = mk_negrisk_event()
        orch.register_market(ev.markets[0])  # one outcome already tracked

        class FakeGamma:
            async def active_markets(self, max_pages=4):
                return []
            async def events(self, closed=False, max_pages=2):
                return [ev,
                        Event(id="ev-other", title="x", neg_risk=True,
                              markets=[mk_market(cid="zz")]),
                        Event(id="ev-not-nr", title="y", neg_risk=False,
                              markets=[mk_market(cid="yy")])]

        orch.gamma = FakeGamma()
        asyncio.run(orch.refresh_markets())
        assert "ev9" in orch.events
        assert "ev-other" not in orch.events       # no tracked overlap
        assert "ev-not-nr" not in orch.events      # not neg-risk
        # every outcome of the tracked event is registered for books
        assert all(m.condition_id in orch.markets for m in ev.markets)
```

Note: `mk_market` in this file sets `event_id="ev1"`; `mk_negrisk_event` overrides to `ev9`. The first test plants asks of 0.30×3 = 0.90 < 1, so S1's `on_event` should emit a 3-leg group; with the fee-free `FREE` schedule the legs pass risk like the existing planted-arb test does.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_orchestrator.py -k NegRisk -v`
Expected: FAIL with `AttributeError: 'Orchestrator' object has no attribute 'events'`

- [ ] **Step 3: Implement.** In `pmtrader/orchestrator.py`:

In `__init__`, after `self._token_market: dict[str, Market] = {}` add:

```python
        self.events: dict[str, object] = {}  # event_id -> neg-risk Event
```

In `on_book` (line ~171), replace the strategy loop with:

```python
        now = book.ts
        positions = dict(self.positions)
        event = self.events.get(market.event_id) if market.event_id else None
        for s in self.strategies:
            ctx = StrategyContext(now=now, cash=self.cash,
                                  budget=self.allocator.budget(s.name),
                                  positions=positions)
            # one buggy strategy must not take down the tick loop (the feed
            # would silently stall while the heartbeat keeps beating)
            try:
                intents = list(s.on_books(market, self.books, ctx))
                if event is not None:
                    intents += list(s.on_event(event, self.books, ctx))
                if intents:
                    self.process_intents(intents, now)
            except Exception as exc:  # noqa: BLE001
                self._strategy_errors[s.name] = \
                    self._strategy_errors.get(s.name, 0) + 1
                log.exception("strategy %s failed on book tick", s.name)
                if self._strategy_errors[s.name] == 1:  # don't spam the log table
                    self.store.insert_decision(now, s.name, "strategy_error", {
                        "error": f"{type(exc).__name__}: {exc}"})
```

In `refresh_markets` (line ~277), replace the body after the `active` registration loop so the feed token list is built **after** event outcomes are registered:

```python
        active.sort(key=lambda m: -m.volume_24h)
        for m in active[: self.cfg.max_tracked_markets]:
            self.register_market(m)
            self.store.upsert_market(m)
        await self._refresh_events()
        if self.feed is not None:
            tokens = []
            for m in list(self.markets.values()):
                tokens += [m.token_id_yes, m.token_id_no]
            self.feed.set_assets(tokens)

    async def _refresh_events(self) -> None:
        """Track neg-risk events that overlap tracked markets and register
        every outcome, so S1 can price the full set (sum of YES asks < 1)."""
        try:
            events = await self.gamma.events(closed=False, max_pages=2)
        except Exception as exc:  # noqa: BLE001
            log.warning("event refresh failed: %s", type(exc).__name__)
            return
        tracked = set(self.markets)
        self.events = {}
        for ev in events:
            if not ev.neg_risk or not ev.markets:
                continue
            if not any(m.condition_id in tracked for m in ev.markets):
                continue
            for m in ev.markets:
                self.register_market(m)
                self.store.upsert_market(m)
            self.events[ev.id] = ev
```

- [ ] **Step 4: Run tests**

Run: `.venv\Scripts\python -m pytest tests/test_orchestrator.py tests/test_s1_arb.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add pmtrader/orchestrator.py tests/test_orchestrator.py
git commit -m "feat(pmtrader): wire neg-risk event dispatch into the tick loop"
```

---

### Task 6: Depth-aware backtest fills

**Files:**
- Modify: `pmtrader/backtest/costs.py`, `pmtrader/backtest/replay.py`
- Test: `tests/test_replay.py` (append; possibly adjust existing tests)

- [ ] **Step 1: Write the failing tests** — append to `tests/test_replay.py` (reuse its existing fixtures/helpers for building a store with markets + price history; follow the file's local conventions for constructing a `ReplayEngine`):

```python
class TestDepthCap:
    def test_synthetic_book_depth_is_finite(self):
        from pmtrader.backtest.costs import CostModel
        from pmtrader.backtest.replay import ReplayEngine
        engine = ReplayEngine.__new__(ReplayEngine)
        engine.cost = CostModel(book_depth=25.0)
        book = ReplayEngine._book(engine, "tok", 0.5, ts=1.0)
        assert book.best_ask_size == 25.0
        assert book.best_bid_size == 25.0

    def test_taker_fill_capped_at_book_depth(self):
        from pmtrader.backtest.costs import CostModel
        from pmtrader.core.models import Intent, Side
        from pmtrader.backtest.replay import ReplayEngine
        from pmtrader.datalayer.store import Store
        import tempfile, pathlib
        tmp = pathlib.Path(tempfile.mkdtemp())
        store = Store(tmp / "d.db")
        engine = ReplayEngine(store, [], CostModel(half_spread=0.0,
                                                   slippage_bps=0.0,
                                                   book_depth=10.0))
        market = mk_market("m1") if "mk_market" in dir() else None
        # build a market inline to be independent of file helpers
        from pmtrader.core.models import Market
        market = Market(condition_id="m1", question="q",
                        token_id_yes="m1-yes", token_id_no="m1-no",
                        fees_enabled=False)
        intent = Intent(strategy="s", token_id="m1-yes", side=Side.BUY,
                        price=0.99, size=100.0, expected_edge=0.01,
                        reasoning="t")
        engine._fill_taker(market, intent, mid=0.5, ts=1.0)
        assert engine.lots and engine.lots[0].size == 10.0
        store.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_replay.py -k DepthCap -v`
Expected: FAIL with `TypeError: ... unexpected keyword argument 'book_depth'`

- [ ] **Step 3: Implement.**

`pmtrader/backtest/costs.py` — update `__init__` and docstring:

```python
class CostModel:
    def __init__(self, half_spread: float = 0.01, slippage_bps: float = 50.0,
                 book_depth: float = 50.0):
        self.half_spread = half_spread
        self.slippage_bps = slippage_bps
        # displayed-depth cap per side: research on Polymarket arb found 76.9%
        # of opportunities executable for only ~15 shares; sampled mids carry
        # no depth, so cap synthetic books rather than assume infinity
        self.book_depth = book_depth
```

`pmtrader/backtest/replay.py`:
- Delete `DEEP = 1_000_000.0  # synthetic book depth` (line 24).
- `_book` (line 120): use `Level(price=bid, size=self.cost.book_depth)` and `Level(price=ask, size=self.cost.book_depth)`.
- `_fill_taker` (line 144): cap size —

```python
    def _fill_taker(self, market: Market, intent: Intent, mid: float, ts: float) -> None:
        price = self.cost.synthetic_quote(mid, intent.side)
        if intent.side == Side.BUY and intent.price < price:
            self.resting.append(RestingOrder(intent, ts))  # limit below market: rests
            return
        if intent.side == Side.SELL and intent.price > price:
            self.resting.append(RestingOrder(intent, ts))
            return
        size = min(intent.size, self.cost.book_depth)
        cash_delta, _fee = self.cost.taker_fill_cost(market, intent.side, price, size)
        self._apply_fill(market, intent, price, cash_delta, ts, size)
```

- `_fill_maker` (line 155): cap size —

```python
    def _fill_maker(self, market: Market, intent: Intent, ts: float) -> None:
        size = min(intent.size, self.cost.book_depth)
        cash_delta, _fee = self.cost.maker_fill_cost(market, intent.side,
                                                     intent.price, size)
        self._apply_fill(market, intent, intent.price, cash_delta, ts, size)
```

- `_apply_fill` (line 160): take `size` explicitly —

```python
    def _apply_fill(self, market: Market, intent: Intent, price: float,
                    cash_delta: float, ts: float, size: float) -> None:
        self.cash += cash_delta
        if intent.side == Side.BUY:
            self.lots.append(Lot(intent.strategy, intent.token_id, size,
                                 -cash_delta, ts))
        else:
            self._close_lots(intent.strategy, intent.token_id, size,
                             cash_delta, ts)
```

Also update the module docstring honesty-limits list: replace "effectively infinite depth" with "finite assumed depth (`CostModel.book_depth`, default 50 shares/side)".

- [ ] **Step 4: Run the replay suite; fix any existing tests that assumed infinite depth** by passing `CostModel(..., book_depth=1_000_000.0)` in those specific tests (do not weaken the new default).

Run: `.venv\Scripts\python -m pytest tests/test_replay.py tests/test_stats.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add pmtrader/backtest/costs.py pmtrader/backtest/replay.py tests/test_replay.py
git commit -m "feat(pmtrader): finite synthetic book depth in backtest fills"
```

---### Task 7: Walk-forward harness — `pmtrader/backtest/walkforward.py`

**Files:**
- Create: `pmtrader/backtest/walkforward.py`
- Test: `tests/test_walkforward.py` (new)

- [ ] **Step 1: Write the failing tests** — create `tests/test_walkforward.py`:

```python
"""Walk-forward gate: K time folds, fresh strategies per fold, pooled CI."""
import pytest

from pmtrader.backtest.costs import CostModel
from pmtrader.backtest.walkforward import run_walkforward
from pmtrader.core.models import Intent, Market, OrderBook, Side
from pmtrader.datalayer.store import Store
from pmtrader.strategies.base import Strategy, StrategyContext


class AlwaysBuy(Strategy):
    """Buys YES once per market at the ask; wins when the market resolves YES."""
    name = "always_buy"

    def __init__(self):
        super().__init__()
        self.done = set()

    def on_books(self, market, books, ctx):
        if market.condition_id in self.done:
            return []
        book = books.get(market.token_id_yes)
        if book is None or book.best_ask is None:
            return []
        self.done.add(market.condition_id)
        return [Intent(strategy=self.name, token_id=market.token_id_yes,
                       side=Side.BUY, price=book.best_ask, size=10.0,
                       expected_edge=0.05, reasoning="t",
                       condition_id=market.condition_id)]


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "wf.db")
    yield s
    s.close()


def seed(store, n_markets=8, span=8000.0):
    """n markets spread over [0, span], each with 3 ticks at 0.40 and a YES
    resolution shortly after its last tick."""
    for i in range(n_markets):
        cid = f"m{i}"
        m = Market(condition_id=cid, question="q", token_id_yes=f"{cid}-y",
                   token_id_no=f"{cid}-n", fees_enabled=False)
        store.upsert_market(m)
        t0 = i * (span / n_markets)
        pts = [(t0 + k * 10.0, 0.40) for k in range(3)]
        store.insert_price_history(m.token_id_yes, pts)
        store.insert_price_history(m.token_id_no, [(t, 1 - p) for t, p in pts])
        store.set_resolution(cid, winning_token_id=m.token_id_yes,
                             resolved_ts=t0 + 40.0)


class TestWalkForward:
    def test_positive_strategy_passes(self, store):
        seed(store)
        report = run_walkforward(store, lambda: [AlwaysBuy()], k=4,
                                 cost=CostModel(half_spread=0.01,
                                                slippage_bps=0.0,
                                                book_depth=50.0),
                                 min_pooled_trades=4, min_fold_trades=1,
                                 min_active_folds=2)
        r = report["strategies"]["always_buy"]
        assert r["n_trades"] >= 4
        assert r["pass"] is True
        assert len(r["fold_ns"]) == 4

    def test_strategy_with_no_trades_fails(self, store):
        seed(store)
        report = run_walkforward(store, lambda: [Strategy()], k=4)
        assert report["strategies"]["base"]["pass"] is False
        assert report["strategies"]["base"]["n_trades"] == 0

    def test_empty_store_reports_error(self, store):
        report = run_walkforward(store, lambda: [AlwaysBuy()], k=4)
        assert report["strategies"] == {}
        assert "error" in report
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_walkforward.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pmtrader.backtest.walkforward'`

- [ ] **Step 3: Create `pmtrader/backtest/walkforward.py`:**

```python
"""Walk-forward backtest gate: the primary, reboot-proof evidence of edge.

Splits stored price history into K equal-duration time folds, replays FRESH
strategy instances over each fold independently, and passes a strategy only
if (a) pooled per-trade P&L has a bootstrap 95% CI lower bound > 0, (b) at
least `min_active_folds` folds traded, and (c) every fold with at least
`min_fold_trades` trades has positive mean P&L. No fold sees another fold's
ticks; settlement uses each market's real resolution (the realized outcome
of a position entered inside the fold, not lookahead for entry decisions).

Honesty limits inherited from the replay engine: sampled mids, synthetic
finite-depth books, pessimistic costs. S2 (microstructure) cannot be judged
here. S4's whitelist was itself derived from this dataset — its headline
evidence is run_calibration_research's internal walk-forward; this harness
re-checks it at execution level only.
"""
from __future__ import annotations

import time
from typing import Callable

from pmtrader.backtest.costs import CostModel
from pmtrader.backtest.replay import ReplayEngine
from pmtrader.backtest.stats import bootstrap_ci
from pmtrader.datalayer.store import Store
from pmtrader.strategies.base import Strategy

MIN_POOLED_TRADES = 30
MIN_FOLD_TRADES = 5
MIN_ACTIVE_FOLDS = 2


def run_walkforward(store: Store,
                    strategy_factory: Callable[[], list[Strategy]],
                    k: int = 4, cost: CostModel | None = None,
                    starting_cash: float = 1000.0,
                    min_pooled_trades: int = MIN_POOLED_TRADES,
                    min_fold_trades: int = MIN_FOLD_TRADES,
                    min_active_folds: int = MIN_ACTIVE_FOLDS) -> dict:
    cost = cost or CostModel()
    lo_ts, hi_ts = store.price_history_span()
    if lo_ts is None or hi_ts is None or hi_ts <= lo_ts:
        return {"error": "no price history in store", "strategies": {}}

    edges = [lo_ts + (hi_ts - lo_ts) * i / k for i in range(k + 1)]
    edges[-1] += 1.0  # inclusive final tick
    acc: dict[str, dict] = {}

    def slot(name: str) -> dict:
        return acc.setdefault(name, {"fold_ns": [0] * k,
                                     "fold_means": [None] * k, "pnls": []})

    for i in range(k):
        strategies = strategy_factory()
        engine = ReplayEngine(store, strategies, cost,
                              start_ts=edges[i], end_ts=edges[i + 1],
                              starting_cash=starting_cash)
        result = engine.run()
        for s in strategies:
            slot(s.name)
        for name, pnls in result.per_strategy_pnl().items():
            d = slot(name)
            d["fold_ns"][i] = len(pnls)
            d["fold_means"][i] = sum(pnls) / len(pnls) if pnls else None
            d["pnls"].extend(pnls)

    out = {"generated_ts": time.time(), "k": k,
           "cost": {"half_spread": cost.half_spread,
                    "slippage_bps": cost.slippage_bps,
                    "book_depth": cost.book_depth},
           "strategies": {}}
    for name, d in acc.items():
        pnls = d["pnls"]
        lo, hi = bootstrap_ci(pnls)
        active = [m for n, m in zip(d["fold_ns"], d["fold_means"])
                  if n >= min_fold_trades and m is not None]
        passed = (len(pnls) >= min_pooled_trades and lo > 0
                  and len(active) >= min_active_folds
                  and all(m > 0 for m in active))
        out["strategies"][name] = {
            "n_trades": len(pnls),
            "mean_pnl": sum(pnls) / len(pnls) if pnls else 0.0,
            "pooled_ci": [lo, hi],
            "fold_ns": d["fold_ns"],
            "fold_means": [None if m is None else round(m, 6)
                           for m in d["fold_means"]],
            "pass": passed,
        }
    return out
```

- [ ] **Step 4: Run tests**

Run: `.venv\Scripts\python -m pytest tests/test_walkforward.py -v`
Expected: 3 PASS. If `test_positive_strategy_passes` fails because folds settle late (resolution after fold end means `_settle` still runs — it does, settlements are loaded per engine), debug with `report` printed; the seed data is constructed so each market's ticks and resolution sit inside one fold.

- [ ] **Step 5: Commit**

```bash
git add pmtrader/backtest/walkforward.py tests/test_walkforward.py
git commit -m "feat(pmtrader): walk-forward backtest gate harness"
```

---

### Task 8: Gate runner script — `scripts/run_walkforward_gate.py`

**Files:**
- Create: `scripts/run_walkforward_gate.py`

- [ ] **Step 1: Create the script** (mirrors `scripts/fetch_history.py` conventions):

```python
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
```

- [ ] **Step 2: Smoke-run it against the real DB**

Run: `.venv\Scripts\python scripts\run_walkforward_gate.py`
Expected: prints a report path and one line per strategy (n may be small until the 1-minute refetch in Task 12; FAIL is an acceptable honest outcome here — the point is the machinery runs).

- [ ] **Step 3: Commit**

```bash
git add scripts/run_walkforward_gate.py
git commit -m "feat(pmtrader): walk-forward gate runner script"
```

---

### Task 9: Paper execution realism report

**Files:**
- Create: `pmtrader/backtest/execution_report.py`
- Create: `scripts/run_execution_report.py`
- Test: `tests/test_execution_report.py` (new)

- [ ] **Step 1: Write the failing tests** — create `tests/test_execution_report.py`:

```python
"""Execution realism report: what paper trading is FOR under backtest-first."""
import pytest

from pmtrader.backtest.execution_report import execution_report
from pmtrader.core.models import Fill, Intent, Order, OrderStatus, Side
from pmtrader.datalayer.store import Store


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "e.db")
    yield s
    s.close()


def put(store, order_id, status, post_only=False, created_ts=100.0,
        fills=()):
    intent = Intent(strategy="s2_mm", token_id="tokA", side=Side.BUY,
                    price=0.50, size=10.0, expected_edge=0.01, reasoning="t",
                    post_only=post_only)
    store.upsert_order(Order(id=order_id, intent=intent, status=status,
                             created_ts=created_ts, updated_ts=created_ts))
    for price, size, ts, maker in fills:
        store.insert_fill(Fill(order_id=order_id, token_id="tokA",
                               side=Side.BUY, price=price, size=size,
                               fee=0.0, ts=ts, maker=maker))


class TestExecutionReport:
    def test_maker_fill_rate_and_time_to_fill(self, store):
        put(store, "paper-r-1", OrderStatus.FILLED, post_only=True,
            created_ts=100.0, fills=[(0.50, 10.0, 160.0, True)])
        put(store, "paper-r-2", OrderStatus.CANCELLED, post_only=True)
        rep = execution_report(store)
        assert rep["makers"]["n_resting_orders"] == 2
        assert rep["makers"]["n_filled"] == 1
        assert rep["makers"]["fill_rate"] == pytest.approx(0.5)
        assert rep["makers"]["median_secs_to_fill"] == pytest.approx(60.0)

    def test_taker_stats(self, store):
        put(store, "paper-r-3", OrderStatus.FILLED,
            fills=[(0.48, 10.0, 100.0, False)])
        rep = execution_report(store)
        assert rep["takers"]["n_orders"] == 1
        # BUY filled 2 cents under the limit -> improvement +0.02/share
        assert rep["takers"]["avg_improvement_per_share"] == pytest.approx(0.02)

    def test_live_orders_excluded(self, store):
        put(store, "0xlive-1", OrderStatus.FILLED,
            fills=[(0.48, 10.0, 100.0, False)])
        rep = execution_report(store)
        assert rep["n_paper_orders"] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_execution_report.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Create `pmtrader/backtest/execution_report.py`:**

```python
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
```

- [ ] **Step 4: Create `scripts/run_execution_report.py`:**

```python
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
```

- [ ] **Step 5: Run tests, then smoke-run the script**

Run: `.venv\Scripts\python -m pytest tests/test_execution_report.py -v`
Expected: 3 PASS
Run: `.venv\Scripts\python scripts\run_execution_report.py`
Expected: JSON with the 11 existing burn-in fills classified.

- [ ] **Step 6: Commit**

```bash
git add pmtrader/backtest/execution_report.py scripts/run_execution_report.py tests/test_execution_report.py
git commit -m "feat(pmtrader): paper execution realism report"
```

---

### Task 10: Surface everything — `__main__` wiring, API endpoints, dashboard UI, decisions-URL bugfix

**Files:**
- Modify: `pmtrader/__main__.py` (after orchestrator construction, line ~88)
- Modify: `pmtrader/api/app.py`
- Modify: `static/app.js` (line 85 bug + strategies renderer line 99), `static/index.html` (line 47 header)
- Test: `tests/test_api.py` (append)

- [ ] **Step 1: Write the failing tests** — append to `tests/test_api.py` (reuse its existing app/client fixture conventions — it builds `build_app(orch, store, cfg)` with a TestClient):

```python
class TestBacktestSurfaces:
    def test_strategies_include_backtest_pass(self, client, orch):
        orch.allocator.set_backtest_pass({"s1_arb": True})
        rows = client.get("/api/strategies").json()
        row = next(r for r in rows if r["name"] == "s1_arb")
        assert row["backtest_pass"] is True

    def test_walkforward_404_without_report(self, client):
        assert client.get("/api/walkforward").status_code in (200, 404)

    def test_execution_report_endpoint(self, client):
        rep = client.get("/api/execution").json()
        assert "makers" in rep and "takers" in rep
```

(If the fixture names differ, match them; the assertions are what matter.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_api.py -v`
Expected: new tests FAIL (`KeyError: 'backtest_pass'`, 404 routes)

- [ ] **Step 3: Implement API changes** in `pmtrader/api/app.py`:

Add imports `import json` at top. After `STATIC_DIR = ...` add:

```python
ROOT_DIR = STATIC_DIR.parent
```

In the `/api/strategies` row dict (line ~64), add:

```python
                "backtest_pass": orch.allocator.backtest_pass.get(name),
```

After the `/api/events` route add:

```python
    @app.get("/api/walkforward")
    def walkforward():
        p = ROOT_DIR / "data" / "walkforward_report.json"
        if not p.exists():
            return JSONResponse(status_code=404, content={
                "error": "no report — run scripts/run_walkforward_gate.py"})
        return json.loads(p.read_text())

    @app.get("/api/execution")
    def execution():
        from pmtrader.backtest.execution_report import execution_report
        return execution_report(store)
```

- [ ] **Step 4: Wire the report into the allocator at startup** in `pmtrader/__main__.py`, after `orch = Orchestrator(...)` (line ~88):

```python
    wf_path = ROOT / "data" / "walkforward_report.json"
    if wf_path.exists():
        wf = json.loads(wf_path.read_text())
        orch.allocator.set_backtest_pass(
            {name: bool(r.get("pass"))
             for name, r in wf.get("strategies", {}).items()})
        log.info("walk-forward gate loaded: %s",
                 {n: r.get("pass") for n, r in wf.get("strategies", {}).items()})
```

- [ ] **Step 5: Fix the UI.** In `static/app.js`:

Line 85 — replace the broken backslash URL:

```javascript
        fetch(`/api/decisions?limit=80${decisionFilter() ? "&strategy=" + decisionFilter() : ""}`),
```

`renderStrategies` (line 99) — add a backtest column:

```javascript
  function renderStrategies(rows) {
    renderRows("strategies-table", rows.map(s => [
      ["", s.name], [`gate-${s.gate}`, s.gate],
      ["", s.backtest_pass === true ? "PASS" : s.backtest_pass === false ? "FAIL" : "—"],
      ["", (s.weight * 100).toFixed(1) + "%"], ["", fmtMoney(s.budget)],
      ["", s.n_paper_trades], ["", s.n_live_trades],
    ]));
  }
```

In `static/index.html` line 47-48, add the header column after Gate:

```html
        <thead><tr><th>Strategy</th><th>Gate</th><th>Backtest</th><th>Weight</th>
          <th>Budget</th><th>Paper n</th><th>Live n</th></tr></thead>
```

- [ ] **Step 6: Run the API tests + full suite**

Run: `.venv\Scripts\python -m pytest tests/test_api.py -v`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add pmtrader/api/app.py pmtrader/__main__.py static/app.js static/index.html tests/test_api.py
git commit -m "feat(pmtrader): surface walk-forward + execution reports; fix decisions URL"
```

---

### Task 11: README runbook

**Files:**
- Modify: `README.md` (runbook section)

- [ ] **Step 1: Add a "Backtest-first validation" section** to the README runbook describing the new flow:

```markdown
## Backtest-first validation (reboot-proof)

The machine this runs on reboots often, so edge evidence never depends on a
continuous burn-in. The pipeline:

1. `python scripts/fetch_history.py --resolved-since <date> --fidelity 1 --max-markets 400`
   — refresh history (1-minute fidelity is only served for recent markets;
   older ones fall back to daily automatically).
2. `python scripts/run_calibration_research.py` — re-derive the S4 whitelist
   (walk-forward internally; political markets show a reverse
   favorite-longshot bias, so expect qualified buckets at high deciles).
3. `python scripts/run_walkforward_gate.py` — the PRIMARY edge gate. Writes
   `data/walkforward_report.json`; strategies that PASS get the reduced
   paper gate (50 trades / 2 days) because paper then only validates
   execution. S2/S3 are excluded (can't be replayed honestly) and keep the
   full 200-trade / 7-day gate.
4. `python scripts/run_execution_report.py` — what paper trading is for:
   maker fill rate, time-to-fill, taker price improvement vs the cost
   model's assumptions. Accumulates across reboots.

Gate evidence is rebuilt from SQLite on every startup
(`Orchestrator.refresh_allocator_trades`), so reboots cost nothing but the
minutes offline. Dashboard: `/api/walkforward`, `/api/execution`, and a
Backtest column in the strategies panel.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs(pmtrader): backtest-first validation runbook"
```

---

### Task 12: Full verification + data runs

- [ ] **Step 1: Full test suite**

Run: `.venv\Scripts\python -m pytest`
Expected: all tests pass (was 304 + ~20 new). Fix anything red before proceeding.

- [ ] **Step 2: Refetch recent history at 1-minute fidelity** (rate-limited, ~5-10 min; resumable if interrupted — that's the point of checkpoints)

Run: `.venv\Scripts\python scripts\fetch_history.py --resolved-since 2026-04-15 --fidelity 1 --max-markets 400`
Expected: `Done: {markets: ..., tokens_fetched: ...}` with errors ≈ 0.

- [ ] **Step 3: Re-derive the S4 whitelist with the enlarged dataset**

Run: `.venv\Scripts\python scripts\run_calibration_research.py`
Expected: report + whitelist regenerated. Sanity-check `data/calibration_report.json`: politics buckets at deciles 5-9 are where the verified reverse favorite-longshot bias predicts qualification; do not hand-add buckets that don't qualify.

- [ ] **Step 4: Run the walk-forward gate for real**

Run: `.venv\Scripts\python scripts\run_walkforward_gate.py`
Expected: per-strategy PASS/FAIL lines and `data/walkforward_report.json`. An honest FAIL is a valid outcome — report it, don't tune until it passes.

- [ ] **Step 5: Boot smoke test** — start the trader briefly, confirm the log line `walk-forward gate loaded: ...`, the dashboard strategies panel shows the Backtest column, and `/api/walkforward` + `/api/execution` respond. Stop it.

- [ ] **Step 6: Final checkpoint commit** of generated reports config (whitelist) if changed:

```bash
git add config/strategies/s4_whitelist.json
git commit -m "chore(pmtrader): regenerated S4 whitelist from enlarged dataset"
```

---

## Self-review notes

- **Spec coverage:** broken allocator wiring → Tasks 1-4; reboot tolerance (durable evidence + reweight clock) → Task 4; neg-risk dead code → Task 5; backtest realism (depth) → Task 6; walk-forward primary gate → Tasks 7-8; paper-as-execution-check → Task 9; dashboard surface → Task 10; 1-min data + whitelist re-derivation → Task 12. The pre-existing `\api\decisions` UI bug is fixed in Task 10.
- **Type consistency:** `closed_trades` returns `{"paper": {...}, "live": {...}}` (Task 2) and is consumed with exactly those keys in Task 4. `Allocator.hydrate(paper, live)` matches. `CostModel.book_depth` (Task 6) is read by `walkforward.py` (Task 7) and `replay.py`.
- **Known risks:** existing `tests/test_replay.py` may assume infinite depth (Task 6 Step 4 handles it); `tests/test_api.py` fixture names must be matched when appending tests; the `trades()` helper signature in `tests/test_allocator.py` must be checked before writing Task 3 tests.
