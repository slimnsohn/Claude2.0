# Polymarket Autonomous Trader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the full multi-strategy autonomous Polymarket trading system per `docs/superpowers/specs/2026-06-09-polymarket-trader-design.md` — paper-mode default, live-ready.

**Architecture:** Single asyncio Python process (strategies → allocator → risk → execution) over a SQLite event store, with a separate watchdog process, a FastAPI dashboard, and a backtest harness that replays history through the same strategy classes. Execution is an interface with `live` and `paper` backends.

**Tech Stack:** Python 3.11+, httpx, websockets, py-clob-client, FastAPI/uvicorn, pydantic v2, numpy, PyYAML, pytest + pytest-asyncio. Vanilla HTML/JS dashboard. SQLite (WAL).

**Execution notes for this session:** User delegated all choices. Default mode = paper. Never log/commit secrets (`POLYMARKET_PRIVATE_KEY`, `POLYMARKET_FUNDER_ADDRESS`). Checkpoint commit at the end of every task (project files only — repo has unrelated dirty files; `git add` explicit paths only, never `-A`). Branch: `feat/polymarket-trader`.

**Project root:** `apps/polymarket-trader/` (all paths below relative to it unless rooted).

---

## Phase 0 — Recon (validate every external assumption)

### Task 0.1: Scaffold project + recon script

**Files:**
- Create: `CLAUDE.md`, `TODO.md`, `README.md`, `requirements.txt`, `pytest.ini`, `.gitignore`, `start.bat`, `pmtrader/__init__.py`, `scripts/recon.py`
- Create: `quick_starts/polymarket-trader_start.bat` (workspace root)

- [ ] **Step 1:** Scaffold from `_skills/scaffold/templates/` (CLAUDE.md ≤50 lines: project one-liner, run commands, env vars list, mode-flip instructions). `requirements.txt`: `httpx`, `websockets`, `py-clob-client`, `fastapi`, `uvicorn[standard]`, `pydantic>=2`, `numpy`, `pyyaml`, `pytest`, `pytest-asyncio`. `.gitignore`: `data/`, `__pycache__/`, `.venv/`, `*.log`. `pytest.ini` sets `asyncio_mode = auto`, `testpaths = tests`.
- [ ] **Step 2:** Create venv, install deps: `python -m venv .venv && .venv\Scripts\pip install -r requirements.txt`. Expected: clean install (py-clob-client pulls web3 deps; allow time).
- [ ] **Step 3:** Write `scripts/recon.py` — read-only probes, no auth needed for public surfaces; prints a findings report and writes `data/recon_findings.json`:
  1. Gamma `GET https://gamma-api.polymarket.com/markets?limit=5&active=true&closed=false` — confirm fields: `conditionId`, `clobTokenIds`, `negRisk`, category/tag fields, `endDate`.
  2. Gamma `GET /events?limit=5&closed=false` — confirm event→markets nesting (neg-risk sets).
  3. CLOB `GET https://clob.polymarket.com/book?token_id=<id from step 1>` — confirm bids/asks shape.
  4. CLOB `GET /prices-history?market=<token_id>&interval=max&fidelity=60` — confirm depth (how far back), point format `{t, p}`.
  5. CLOB `GET /markets/<condition_id>` — confirm fee fields (`maker_base_fee`, `taker_base_fee` or current names), `neg_risk` flag, tick size, min order size.
  6. Sample a resolved market via Gamma (`closed=true`) — confirm resolution outcome fields (`outcomePrices` or equivalent) usable as ground truth for backtests.
  7. Binance `GET https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1m&limit=5` — reachable, shape.
  8. WSS smoke: connect `wss://ws-subscriptions-clob.polymarket.com/ws/market`, subscribe one token, confirm ≥1 `book` message within 30s.
- [ ] **Step 4:** Run `.venv\Scripts\python scripts/recon.py`. Expected: all 8 probes PASS with findings JSON written. If any endpoint shape differs from spec assumptions, record the actual shape in `data/recon_findings.json` and use the actual shape in all later tasks.
- [ ] **Step 5:** Commit: `git add apps/polymarket-trader quick_starts/polymarket-trader_start.bat && git commit -m "feat(pmtrader): scaffold + API recon"`.

---

## Phase 1 — Core models, fees, store, REST clients, history fetcher

### Task 1.1: Core domain models

**Files:**
- Create: `pmtrader/core/__init__.py`, `pmtrader/core/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1:** Failing tests for models — construct each, assert invariants:

```python
def test_intent_requires_reasoning():
    with pytest.raises(ValidationError):
        Intent(strategy="s1", token_id="t", side=Side.BUY, price=0.5, size=10,
               expected_edge=0.02, reasoning="")  # empty reasoning rejected

def test_order_book_best_and_mid():
    book = OrderBook(token_id="t", ts=1.0,
                     bids=[Level(price=0.48, size=100)], asks=[Level(price=0.52, size=80)])
    assert book.best_bid == 0.48 and book.best_ask == 0.52 and book.mid == 0.50

def test_order_book_microprice_weights_by_size():
    book = OrderBook(token_id="t", ts=1.0,
                     bids=[Level(price=0.40, size=300)], asks=[Level(price=0.60, size=100)])
    assert book.microprice == pytest.approx(0.40 + (0.60-0.40)*300/400)  # 0.55

def test_price_bounds():
    with pytest.raises(ValidationError):
        Intent(strategy="s1", token_id="t", side=Side.BUY, price=1.2, size=10,
               expected_edge=0.01, reasoning="x")
```

- [ ] **Step 2:** Run `pytest tests/test_models.py -v` → FAIL (imports missing).
- [ ] **Step 3:** Implement pydantic models: `Side(StrEnum)` BUY/SELL; `Level(price, size)`; `OrderBook(token_id, ts, bids, asks)` with `best_bid/best_ask/mid/microprice` properties (microprice = weighted by opposite-side size: `(bid*ask_sz + ask*bid_sz)/(bid_sz+ask_sz)`... use standard: `(best_bid*ask_size + best_ask*bid_size)/(bid_size+ask_size)`); `Market(condition_id, question, category, token_id_yes, token_id_no, neg_risk, end_date, taker_fee_rate, maker_fee_rate, tick_size, min_size, active)`; `Intent(strategy, token_id, side, price∈(0,1), size>0, expected_edge, reasoning min_length=1, tif, post_only=False)`; `Order(id, intent, status, filled_size, avg_fill_price, created_ts, updated_ts)`; `Fill(order_id, token_id, side, price, size, fee, ts, maker)`; `Position(token_id, size, avg_cost)`.
- [ ] **Step 4:** `pytest tests/test_models.py -v` → PASS.
- [ ] **Step 5:** Commit `feat(pmtrader): core domain models`.

### Task 1.2: Fee math

**Files:**
- Create: `pmtrader/core/fees.py`
- Test: `tests/test_fees.py`

- [ ] **Step 1:** Failing tests pinning the published schedule (peak $ per 100 shares at p=0.5; quadratic profile `4·peak·p·(1−p)`):

```python
def test_crypto_taker_fee_peak():
    # $1.80 per 100 shares at p=0.5 → 0.018/share
    assert taker_fee_per_share(price=0.5, category="crypto") == pytest.approx(0.018)

def test_fee_decreases_toward_extremes():
    assert taker_fee_per_share(0.9, "crypto") == pytest.approx(4*0.018*0.9*0.1)
    assert taker_fee_per_share(0.99, "crypto") < taker_fee_per_share(0.6, "crypto")

def test_geopolitics_free():
    assert taker_fee_per_share(0.5, "geopolitics") == 0.0

def test_maker_fee_zero_everywhere():
    assert maker_fee_per_share(0.5, "crypto") == 0.0

def test_market_rate_overrides_category():
    # when the API reports an explicit rate for a market, it wins
    assert taker_fee_per_share(0.5, "crypto", market_rate_per_share_peak=0.01) == pytest.approx(0.01)

def test_order_fee_total():
    assert order_taker_fee(price=0.5, size=200, category="sports") == pytest.approx(200*0.0075)
```

- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement:

```python
PEAK_PER_SHARE = {  # $/share at p=0.5, from published schedule 2026-06; API rate overrides
    "crypto": 0.018, "economics": 0.0125, "culture": 0.0125, "weather": 0.0125,
    "politics": 0.010, "finance": 0.010, "tech": 0.010, "mentions": 0.010,
    "sports": 0.0075, "geopolitics": 0.0, "world": 0.0,
}
DEFAULT_PEAK = 0.0125  # unknown category → assume mid-tier, conservative

def taker_fee_per_share(price, category, market_rate_per_share_peak=None):
    peak = market_rate_per_share_peak if market_rate_per_share_peak is not None \
           else PEAK_PER_SHARE.get(category.lower(), DEFAULT_PEAK)
    return 4.0 * peak * price * (1.0 - price)

def maker_fee_per_share(price, category, market_rate_per_share_peak=None):
    return 0.0

def order_taker_fee(price, size, category, market_rate_per_share_peak=None):
    return size * taker_fee_per_share(price, category, market_rate_per_share_peak)
```

(If recon found explicit per-market fee fields with different semantics, adapt to the recon-confirmed semantics and note it in the module docstring.)
- [ ] **Step 4:** Run → PASS. **Step 5:** Commit `feat(pmtrader): fee model`.

### Task 1.3: SQLite store + raw archive

**Files:**
- Create: `pmtrader/datalayer/__init__.py`, `pmtrader/datalayer/store.py`, `pmtrader/datalayer/archive.py`
- Test: `tests/test_store.py`

- [ ] **Step 1:** Failing tests: `Store(path)` creates schema (tables: `markets`, `price_history(token_id, ts, price)`, `intents`, `orders`, `fills`, `equity_snapshots`, `decisions(ts, strategy, kind, payload_json)`, `strategy_stats`); insert/fetch roundtrip for a Market, an Intent (+reasoning persisted), a Fill; `equity_curve()` returns ordered snapshots; WAL mode on; `Archive(dir)` writes gzipped raw JSON named `{surface}/{date}/{ts}_{tag}.json.gz` and can list/read back.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement with `sqlite3`, single connection, `PRAGMA journal_mode=WAL`, thread-safe via `threading.Lock` (async code calls through `asyncio.to_thread`). All writes parameterized. JSON columns for nested payloads.
- [ ] **Step 4:** Run → PASS. **Step 5:** Commit `feat(pmtrader): sqlite store + raw archive`.

### Task 1.4: Gamma + CLOB REST clients

**Files:**
- Create: `pmtrader/datalayer/gamma.py`, `pmtrader/datalayer/clob_rest.py`
- Test: `tests/test_gamma.py`, `tests/test_clob_rest.py` (httpx MockTransport fixtures built from recon-captured real payloads saved under `tests/fixtures/`)

- [ ] **Step 1:** Save trimmed real recon responses as fixtures. Failing tests: `GammaClient.active_markets()` → list[Market] with fees/category/token ids parsed; `GammaClient.events(closed=False)` groups neg-risk sets; `GammaClient.resolved_markets(since)` yields (Market, winning_token_id); `ClobRestClient.book(token_id)` → OrderBook; `ClobRestClient.prices_history(token_id, fidelity=60)` → list[(ts, price)]; retry-with-backoff on 429/5xx (test with MockTransport returning 429 then 200); timeout raises typed `DataError`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement async clients on `httpx.AsyncClient`, paginate Gamma (`limit`/`offset`), parse defensively (recon-confirmed field names; missing fee field → None, fees.py default applies). Backoff: 3 retries, 0.5→2→8s.
- [ ] **Step 4:** Run → PASS. **Step 5:** Commit `feat(pmtrader): gamma + clob REST clients`.

### Task 1.5: History fetcher script

**Files:**
- Create: `scripts/fetch_history.py`
- Test: `tests/test_fetch_history.py` (unit-test the planning/resume logic with mocked clients)

- [ ] **Step 1:** Failing tests: given a mocked Gamma returning 3 resolved + 2 active markets, fetcher requests prices-history for each token once, stores points + resolution outcomes in Store, archives raw, and **resumes** (second run with same data fetches nothing new — checkpoint table).
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement: CLI `--categories all --resolved-since 2024-01-01 --fidelity 60 --max-markets N`, polite rate limiting (≤5 req/s), progress logging, resumable via `fetch_checkpoints` table.
- [ ] **Step 4:** Run tests → PASS. **Step 5:** Run it for real (bounded): `--max-markets 500` across categories to populate `data/pmtrader.db`; record actual history depth found in `data/recon_findings.json`. **Step 6:** Commit `feat(pmtrader): historical data fetcher`.

---

## Phase 2 — Backtest harness + statistics

### Task 2.1: Statistics module (bootstrap CI, walk-forward)

**Files:**
- Create: `pmtrader/backtest/__init__.py`, `pmtrader/backtest/stats.py`
- Test: `tests/test_stats.py`

- [ ] **Step 1:** Failing tests:

```python
def test_bootstrap_ci_contains_mean_for_positive_sample():
    rng_trades = [0.01]*150 + [-0.005]*50          # clearly positive EV
    lo, hi = bootstrap_ci([float(x) for x in rng_trades], n_boot=2000, alpha=0.05, seed=7)
    assert lo > 0 and lo < statistics.mean(rng_trades) < hi

def test_bootstrap_ci_straddles_zero_for_noise():
    lo, hi = bootstrap_ci([0.01, -0.01]*100, n_boot=2000, alpha=0.05, seed=7)
    assert lo < 0 < hi

def test_bootstrap_deterministic_with_seed():
    xs = [0.01, -0.02, 0.03]*40
    assert bootstrap_ci(xs, seed=1) == bootstrap_ci(xs, seed=1)

def test_walk_forward_windows_never_overlap_eval():
    folds = walk_forward(n=1000, train=400, test=200)
    for tr, te in folds:
        assert max(tr) < min(te)          # strictly out-of-sample
    assert len(folds) == 3
```

- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement with `numpy.random.default_rng(seed)`; `bootstrap_ci` resamples mean; `walk_forward` returns index ranges; add `max_drawdown(equity)` and `sharpe(returns)` helpers with tests for each (drawdown of [1,1.2,0.9,1.1] → 0.25; sharpe of constant returns → inf guard returns large finite cap).
- [ ] **Step 4:** PASS. **Step 5:** Commit `feat(pmtrader): bootstrap/walk-forward stats`.

### Task 2.2: Cost model + replay engine

**Files:**
- Create: `pmtrader/backtest/costs.py`, `pmtrader/backtest/replay.py`
- Test: `tests/test_replay.py`

- [ ] **Step 1:** Failing tests:
  - `CostModel.taker_fill(price, size, category)` returns fill cost = notional + fee + slippage haircut (`slippage_bps` config, default 50bps of notional).
  - Replay: feed a synthetic price series for one token + a `BuyAndHoldToResolution` toy strategy; engine emits ticks chronologically, collects intents, fills them via CostModel, marks to market, settles at resolution price (0 or 1), and produces `BacktestResult(trades, equity_curve, per_trade_pnl)` where final equity matches hand-computed value **exactly** (write the arithmetic in the test).
  - Determinism: two runs → identical results.
  - No-lookahead: strategy receives only data with `ts <= now` (test with a probe strategy that asserts monotonic ts).
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement `ReplayEngine(store, strategies, cost_model, start, end)`: iterates stored price points as ticks; maker fills modeled pessimistically (resting order fills only if a later tick price strictly crosses it); taker fills at tick price + costs; settles on resolution; outputs `BacktestResult` with `stats.bootstrap_ci` applied to per-trade P&L.
- [ ] **Step 4:** PASS. **Step 5:** Commit `feat(pmtrader): backtest replay + cost model`.

---

## Phase 3 — Strategy framework, S1 + S4 research

### Task 3.1: Strategy base + S1 arb scanner

**Files:**
- Create: `pmtrader/strategies/__init__.py`, `pmtrader/strategies/base.py`, `pmtrader/strategies/s1_arb.py`
- Test: `tests/test_s1_arb.py`

- [ ] **Step 1:** Failing tests (golden books):

```python
def make_pair_books(yes_ask, no_ask, depth=500):
    ...  # OrderBook fixtures for YES and NO tokens of one market

def test_s1_fires_on_cheap_pair():
    # YES ask 0.46 + NO ask 0.50 = 0.96; geopolitics (fee 0) → locked 0.04/share minus ε
    intents = s1.on_books(market_geo, make_pair_books(0.46, 0.50))
    assert len(intents) == 2 and all(i.side == Side.BUY for i in intents)
    assert intents[0].size == intents[1].size            # matched legs
    assert "sum=0.9600" in intents[0].reasoning

def test_s1_respects_fees_in_taxed_category():
    # sum 0.985 looks <1 but crypto taker fees at these prices exceed the 0.015 gross edge
    assert s1.on_books(market_crypto, make_pair_books(0.485, 0.50)) == []

def test_s1_sizes_to_book_depth():
    books = make_pair_books(0.46, 0.50, depth=120)
    intents = s1.on_books(market_geo, books)
    assert intents[0].size <= 120

def test_s1_negrisk_set_buy_all_yes():
    # 4-outcome event, YES asks sum to 0.93 → buy all four
    intents = s1.on_event(event4, books4)
    assert len(intents) == 4

def test_s1_no_fire_when_sum_above_one():
    assert s1.on_books(market_geo, make_pair_books(0.52, 0.50)) == []
```

- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement `Strategy` base (`name`, `on_books`, `on_event`, `on_fill`, `on_timer`, param dict with declared bounds) and S1 logic: edge = `1 − Σasks − Σfees(ask_i) − ε` (ε config, default 0.005); size = min(depth at ask across legs, budget); both legs emitted atomically with shared `group_id` so execution can unwind if one leg fails.
- [ ] **Step 4:** PASS. **Step 5:** Commit `feat(pmtrader): strategy base + S1 arb scanner`.

### Task 3.2: S4 calibration research + strategy

**Files:**
- Create: `pmtrader/strategies/s4_calib.py`, `scripts/run_calibration_research.py`
- Test: `tests/test_s4_calib.py`

- [ ] **Step 1:** Failing tests: `calibration_table(resolved_rows)` buckets by (category, price decile, days-to-resolution band) and returns hit-rate + count + Wilson CI per bucket; `S4.on_books` fires only for buckets pre-listed in its config whitelist where `wilson_lo − price − fee > margin`; sizing respects tight per-event cap; reasoning cites bucket stats.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement table + strategy; whitelist loaded from `config/strategies/s4.yaml` (empty whitelist = strategy inert).
- [ ] **Step 4:** PASS. **Step 5:** Run `scripts/run_calibration_research.py` against fetched history with walk-forward splits; write `data/calibration_report.json` + human summary. **Decision gate (D): populate s4.yaml whitelist only with buckets whose bias survives all folds after fees; if none survive, whitelist stays empty and S4 ships inert — record the finding.** **Step 6:** Backtest S1 against history (limitation: sampled mids approximate books; treat result as smoke test). **Step 7:** Commit `feat(pmtrader): S4 calibration research + strategy`.

---

## Phase 4 — Execution, risk, paper simulator, WSS feeds

### Task 4.1: Order state machine

**Files:**
- Create: `pmtrader/execution/__init__.py`, `pmtrader/execution/state_machine.py`
- Test: `tests/test_state_machine.py` (100% branch coverage required)

- [ ] **Step 1:** Failing tests covering every legal transition and every illegal one:
  - CREATED→SUBMITTED→OPEN→PARTIALLY_FILLED→FILLED; OPEN→CANCELLED; SUBMITTED→REJECTED; OPEN→EXPIRED; PARTIALLY_FILLED→CANCELLED (remainder).
  - Illegal (e.g., FILLED→OPEN) raises `InvalidTransition`.
  - `apply_fill` accumulates `filled_size`/`avg_fill_price` correctly (two partial fills 60@0.40 + 40@0.42 → avg 0.408).
  - Overfill (fill > remaining) raises.
  - `reconcile(api_state)` resolves divergence: API says FILLED while local OPEN → emit synthetic fill for the gap and land in FILLED; API unknown order → mark EXPIRED-orphan and flag for ops.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement explicit transition table; every transition appends to an audit list `(ts, from, to, why)`.
- [ ] **Step 4:** `pytest --cov=pmtrader/execution/state_machine --cov-branch` → 100%. **Step 5:** Commit `feat(pmtrader): order state machine`.

### Task 4.2: Risk manager

**Files:**
- Create: `pmtrader/risk.py`, `pmtrader/core/bankroll.py`
- Test: `tests/test_risk.py`, `tests/test_bankroll.py` (100% branch coverage required on both)

- [ ] **Step 1:** Failing tests — one per rule in spec §7, each with an approving case and a vetoing case. Exact rule set and defaults:

```python
RULES = dict(max_market_frac=0.05, max_event_frac=0.10, max_at_risk_frac=0.80,
             daily_loss_halt_frac=0.10, max_book_frac=0.25, stale_book_sec=10,
             kelly_fraction=0.25, resolution_blackout_min=10)

def test_veto_negative_ev_after_fees(): ...      # intent edge 0.001, fee 0.009 → veto "EV<=0"
def test_veto_market_exposure_cap(): ...          # would exceed 5% bankroll in one market
def test_veto_event_exposure_cap(): ...           # correlated tokens same event > 10%
def test_veto_total_at_risk(): ...
def test_halt_on_daily_loss(): ...                # realized day pnl <= -10% → ALL intents vetoed + halt flag
def test_veto_size_vs_depth(): ...                # size > 25% displayed depth at level
def test_veto_stale_book(): ...                   # book ts older than 10s
def test_veto_resolution_blackout_except_s1_unwind(): ...
def test_kelly_downsizes_not_upsizes(): ...       # approved size = min(requested, kelly_cap)
def test_approval_passes_all_and_logs_reasoning(): ...
```

  `Bankroll` tests: equity = cash + Σ marks; double-or-bust `check(equity)` returns CONTINUE / STOP_WON (≥2·E₀) / STOP_LOST (≤0.05·E₀); day-boundary P&L reset.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement `RiskManager.check(intent, snapshot) -> Approved(size)|Veto(rule, detail)`; pure function over a `PortfolioSnapshot` (cash, positions, marks, day_pnl, books) — no I/O, fully unit-testable. Kelly cap: `f* = edge / odds_variance` simplified for binary: `f* = (p_model − price)/ (price·(1−price))` × bankroll × kelly_fraction, capped by other rules.
- [ ] **Step 4:** `pytest --cov=pmtrader/risk --cov=pmtrader/core/bankroll --cov-branch` → 100%. **Step 5:** Commit `feat(pmtrader): risk manager + bankroll policy`.

### Task 4.3: WSS market/user feeds

**Files:**
- Create: `pmtrader/datalayer/clob_ws.py`, `pmtrader/datalayer/binance.py`
- Test: `tests/test_clob_ws.py` (against a local fake WSS server fixture replaying recorded frames)

- [ ] **Step 1:** Record ~2 min of real market-channel frames via a throwaway script into `tests/fixtures/wss_market_sample.jsonl` (and keep for the paper-sim test). Failing tests: client maintains `BookCache` (apply snapshot + deltas → matches expected book at known frame indexes); detects silence > N sec → emits `StaleFeed` event; auto-reconnects after server drop and re-subscribes; user-channel frames produce typed `OrderUpdate`/`TradeUpdate` events.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement with `websockets`, heartbeat watchdog task, bounded resubscribe backoff. Binance: kline WSS + REST backfill into store (test parse only).
- [ ] **Step 4:** PASS. **Step 5:** Commit `feat(pmtrader): WSS feeds + book cache`.

### Task 4.4: Execution backends (paper + live)

**Files:**
- Create: `pmtrader/execution/paper.py`, `pmtrader/execution/live.py`, `pmtrader/execution/router.py`
- Test: `tests/test_paper_exec.py`, `tests/test_live_exec.py` (live client fully mocked — no network in tests)

- [ ] **Step 1:** Failing tests, paper backend (the critical one):
  - Marketable buy at ask → immediate fill at ask, walks depth for size > level, taker fee applied from fees.py.
  - Resting bid fills **only when a trade prints at price ≤ bid** (feed trade frames from fixture) — touch without trade ≠ fill; partial fill when print size < order size.
  - Cancel removes resting order; `cancel_all()` empties book of our orders.
  - Fills update Store and emit events identical in shape to live backend's.
  - Group unwind: if leg A of a `group_id` pair fills and leg B is rejected, paper backend reports it and router emits an unwind intent (market-sell leg A) — test the router rule.
  - Live backend tests (mocked `py-clob-client`): order params mapped correctly (token_id, price→tick-rounded, size, side, post_only); cancel-all called on `close()`; API error → order REJECTED not crash; **assert private key never appears in any log record** (capture logs, scan).
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement `ExecutionBackend` protocol: `submit(intent)->Order`, `cancel(id)`, `cancel_all()`, `positions()`, events stream. Router holds backend by mode, enforces group semantics, persists everything.
- [ ] **Step 4:** PASS (state machine cov stays 100%). **Step 5:** Commit `feat(pmtrader): paper + live execution backends`.

---

## Phase 5 — S2 market maker + S3 crypto fair value

### Task 5.1: S2 market maker

**Files:**
- Create: `pmtrader/strategies/s2_mm.py`
- Test: `tests/test_s2_mm.py`

- [ ] **Step 1:** Failing tests:
  - Given calm book fixture → emits one bid + one ask around microprice with spread = `max(min_spread, k·σ_ref)`; both post_only.
  - Inventory skew: long 400 shares → both quotes shift down by `γ·inv·σ²·τ` (assert direction + monotonicity in inv).
  - Markout monitor: feed fills + later mids where markout avg < −threshold → strategy widens spread multiplier and below 2× threshold → emits no quotes (pulled) + reasoning logged.
  - Requote only when reference moved ≥ tick or inventory changed (no churn: same book twice → no new intents).
  - Market selection: `select_markets(candidates)` filters by volume floor, ≥48h to end, rebate-eligible flag, catalyst blacklist from config.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement with params (bounds in `config/strategies/s2.yaml`): `gamma`, `k_spread`, `min_spread`, `max_inventory`, `markout_threshold`, `markout_window`. σ_ref = EWMA std of microprice changes.
- [ ] **Step 4:** PASS. **Step 5:** Commit `feat(pmtrader): S2 market maker`.

### Task 5.2: S3 crypto fair value

**Files:**
- Create: `pmtrader/strategies/s3_crypto.py`
- Test: `tests/test_s3_crypto.py`

- [ ] **Step 1:** Failing tests:

```python
def test_fair_value_atm_is_half():
    assert fair_value(spot=100_000, strike=100_000, sigma_ann=0.5, tau_years=1/365) == pytest.approx(0.5, abs=1e-9)

def test_fair_value_monotonic_in_spot(): ...
def test_fair_value_known_case():
    # S=105k, K=100k, σ=60%, τ=7/365 → d = ln(1.05)/(0.6*sqrt(7/365)); P=Φ(d) — assert to 1e-6 vs scipy-free Φ
def test_ewma_vol_estimator_matches_hand_calc(): ...   # 5 returns, λ=0.94
def test_no_trade_inside_band(): ...                   # |market−fair| < fee+halfspread+margin → []
def test_trade_fires_with_full_reasoning(): ...        # divergence 6¢, band 3¢ → intent, reasoning has fair, σ, τ, fees
def test_vol_regime_guard_widens_band(): ...           # vol-of-vol high → margin multiplied, prior trade now suppressed
def test_prefers_maker_inside_divergence(): ...        # large book spread → post_only intent priced inside, not taker
```

- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement `Φ` via `math.erf`; EWMA vol from Binance 1m closes annualized; parse strike + direction from market metadata (recon-confirmed fields; unparseable market → skip with logged reason).
- [ ] **Step 4:** PASS. **Step 5:** Backtest S3 against fetched crypto-market history + Binance klines, walk-forward; record CI report in `data/backtest_s3_report.json`. Gate per spec: validation CI lower bound > 0 else ships disabled. **Step 6:** Commit `feat(pmtrader): S3 crypto fair value + backtest report`.

---

## Phase 6 — Allocator, orchestrator, watchdog

### Task 6.1: Allocator

**Files:**
- Create: `pmtrader/allocator.py`
- Test: `tests/test_allocator.py`

- [ ] **Step 1:** Failing tests: equal weights at start; after injecting trade histories (A: strong +EV n=300, B: noise n=300, C: negative n=300) reweight → w_A > w_B > w_C with floor 0.05 / cap 0.50 respected and Σw=1 over enabled strategies; shrinkage: n=10 strong record moves weight less than n=300 same mean; edge-decay: rolling CI upper < 0 → strategy demoted to paper (allocator emits `Demotion(reason, evidence)`); demoted strategy re-passes gate (≥200 paper trades, CI lo > 0, ≥7 days) → re-promoted; all transitions persisted to decisions table.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement: score = shrunk Sharpe `(n/(n+k))·mean/std·√n` k=100; weights = softmax(score/T) clipped to [0.05, 0.50] renormalized; weekly timer + on-demand.
- [ ] **Step 4:** PASS. **Step 5:** Commit `feat(pmtrader): capital allocator with edge-decay gates`.

### Task 6.2: Orchestrator + config + watchdog

**Files:**
- Create: `pmtrader/orchestrator.py`, `pmtrader/config.py`, `pmtrader/__main__.py`, `watchdog.py`, `config/settings.yaml`, `config/strategies/{s1,s2,s3,s4}.yaml`
- Test: `tests/test_orchestrator.py`, `tests/test_config.py`

- [ ] **Step 1:** Failing tests: config loads + validates (mode ∈ {backtest, paper, live}; live mode additionally requires env vars present and `live_armed: true` — both, else startup refuses with clear error); orchestrator wires feeds→strategies→allocator→risk→execution and a full tick-to-fill loop runs in paper mode with fake feed (integration-style test, asserts an intent flowed through and a decision row was persisted); halt flag from risk stops new intents but allows cancels; shutdown path calls `cancel_all` exactly once per backend; heartbeat file touched every loop; SIGTERM-equivalent clean exit.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement; `watchdog.py` is a small stdlib-only process: starts main, watches heartbeat mtime (>60s stale → kill + restart, max 5 restarts/hour then stop + loud log), used by `start.bat`. On main-process start in paper/live: reconcile open orders via REST before strategies start.
- [ ] **Step 4:** PASS. **Step 5:** Commit `feat(pmtrader): orchestrator + watchdog + config`.

---

## Phase 7 — Dashboard

### Task 7.1: Dashboard API + UI

**Files:**
- Create: `pmtrader/api/__init__.py`, `pmtrader/api/app.py`, `static/index.html`, `static/app.js`, `static/styles.css`
- Test: `tests/test_api.py` (FastAPI TestClient)

- [ ] **Step 1:** Failing tests: `GET /api/state` → JSON {mode, equity, bankroll_progress (double-or-bust), positions, open_orders, halt}; `GET /api/strategies` → per-strategy {pnl, weight, gate_status, ci}; `GET /api/decisions?limit=100` → newest-first decision log incl. vetoes; `POST /api/control/kill` with token → cancel-all + halt (wrong token → 403); `POST /api/control/mode` guarded same way; WS `/ws` pushes state snapshot ≥1/2s (test receives one).
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement FastAPI app mounted by orchestrator (same process, uvicorn task, binds 127.0.0.1:8765 by default; LAN bind via config). UI: vanilla JS, panels per spec §9 (equity chart via lightweight canvas drawing, no heavy deps), kill-switch button with confirm, decision log table with strategy filter, chat widget script tag from `_skills/llm-chat-widget/`.
- [ ] **Step 4:** PASS; manual check: `start.bat` opens browser, dashboard renders with paper-mode data. **Step 5:** Commit `feat(pmtrader): dashboard API + UI`.

---

## Phase 8 — Integration, burn-in, docs, audit

### Task 8.1: End-to-end integration test + full suite

- [ ] **Step 1:** `tests/test_integration_paper.py`: spin orchestrator in paper mode with recorded WSS replay fixture + canned Gamma/REST mocks; assert: books flow, ≥1 S1 intent on a planted arb in the fixture, risk approves, paper fill lands, equity updates, dashboard `/api/state` reflects it, decision log complete; clean shutdown cancels resting orders.
- [ ] **Step 2:** Full suite `pytest --cov=pmtrader --cov-branch` → all pass; 100% branch on risk.py, fees.py, state_machine.py, bankroll.py; record overall coverage number in TODO.md.
- [ ] **Step 3:** Commit `test(pmtrader): end-to-end paper integration`.

### Task 8.2: README, runbook, security audit

- [ ] **Step 1:** README: setup (env vars incl. how to export Polymarket key — with warnings), start.bat usage, mode progression backtest→paper→live, gate criteria, what every dashboard panel means, kill switch, recovery behavior, known limitations (backtest book approximation; S2 judged in paper only).
- [ ] **Step 2:** Run security-audit skill (workspace rule before deploy/live): secrets scan, .gitignore correctness, dashboard auth token, no key in logs.
- [ ] **Step 3:** Update project TODO.md: "Now: paper burn-in running; live flip requires gates + user." Final commit `docs(pmtrader): README + runbook`; leave system running in paper mode.

---

## Self-review (done at write time)

- **Spec coverage:** §2 fees→Task 1.2; §3 APIs→0.1/1.4/4.3; §4 architecture→1.x/4.x/6.2; §5 S1→3.1, S2→5.1, S3→5.2, S4→3.2; §6 allocator→6.1; §7 risk table→4.2 (every row has a test); §8 backtest/stats→2.x + gates in 3.2/5.2/6.1; §9 dashboard→7.1; §10 testing→per-task TDD + 8.1; §11 build order = phase order. No gaps found.
- **Placeholder scan:** no TBDs; recon-dependent field names are explicitly deferred to recon findings by instruction, not left vague.
- **Type consistency:** Intent/Order/Fill/OrderBook defined once in Task 1.1 and referenced consistently; `ExecutionBackend` protocol named identically in 4.4/6.2; fee function names consistent across 1.2/2.2/4.4.
