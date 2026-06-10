# Polymarket Autonomous Trader — Design

**Date:** 2026-06-09
**Project:** `apps/polymarket-trader`
**Intent:** Fully autonomous multi-strategy trading system for Polymarket (international). Connects to the user's account, runs unattended 24/7 on Windows, trades via market making and model-driven taking, with a capital allocator that learns which edges are real. Backtest → paper → live progression with statistical gates. Optional "double-or-bust" bankroll mode.

**User delegation note:** User approved Approach B (multi-strategy engine + allocator) and the Section 1 architecture, then delegated all remaining design decisions: "you make all recommended selections and build entire system." Decisions below marked (D) are delegated picks.

---

## 1. Goals & Non-Goals

**Goals**
- Net **profit after fees** — every EV calculation is fee- and spread-adjusted. Academic edge that doesn't survive costs is a bug.
- Edge must be **real, not spurious**: pre-specified strategies, walk-forward validation, bootstrap confidence intervals, statistical paper-trading gate before live.
- Runs unattended on the user's Windows PC: watchdog, auto-restart, cancel-all on disconnect, full state recovery from SQLite.
- Browser dashboard: equity, positions, orders, per-strategy P&L/allocation, decision log with reasoning, risk status, kill switch, mode control.
- Configurable bankroll; **paper mode is the default**; live trading requires explicit config flip.

**Non-Goals (v1)**
- News/information trading, LLM-driven market opinions.
- Unsupervised strategy discovery / end-to-end ML price prediction (rejected as spurious-edge factory).
- Cross-platform arb (Kalshi etc.), on-chain CTF split/merge minting (v1 trades only via CLOB orders).
- Mobile UI, multi-account support.

---

## 2. Market & Fee Reality (verified 2026-06)

- Taker fees per category, peak at p=0.50: crypto $1.80/100 shares, economics/culture/weather $1.25, politics/finance/tech/mentions $1.00, sports $0.75, **geopolitics/world events: $0**. Formula: `fee = shares × feeRate × p × (1−p)` (feeRate = category peak rate ×4 in per-share terms).
- **Maker fees: zero.** Maker rebate program: 25% of collected fees (20% on crypto) redistributed daily to makers.
- Consequences baked into design: market making is rebate-subsidized; taker strategies face the largest fee exactly at maximum uncertainty; the arb scanner hunts primarily fee-free categories; **fee schedule is fetched per-market from the API at runtime, never hardcoded** (Polymarket changes it).

## 3. APIs (verify empirically in Phase 0 recon)

| Surface | Use |
|---|---|
| Gamma API `gamma-api.polymarket.com` | Market/event metadata, categories, resolution outcomes, neg-risk structure |
| CLOB REST `clob.polymarket.com` | Order books, order placement/cancel (via `py-clob-client`), fee rates, prices-history, rewards/markets |
| CLOB WSS `ws-subscriptions-clob.polymarket.com` | `market` channel (books, trades), `user` channel (own fills/order updates) |
| Data API `data-api.polymarket.com` | Trade history, positions |
| Binance REST/WSS | BTC/ETH spot candles + live price for S3 fair value |

Auth: wallet private key + funder address via Windows env vars (`POLYMARKET_PRIVATE_KEY`, `POLYMARKET_FUNDER_ADDRESS`, `POLYMARKET_SIGNATURE_TYPE`). Email-login accounts must export their key from Polymarket settings (documented in README). Never hardcoded, never committed, never logged.

Phase 0 of the implementation is a **recon script** that empirically confirms every endpoint, auth flow, fee field, and historical-data depth before anything is built on top. Findings get written back into this spec's companion notes.

---

## 4. Architecture

```
apps/polymarket-trader/
├── CLAUDE.md / TODO.md / README.md / start.bat
├── config/
│   ├── settings.yaml          # mode, bankroll, risk limits, strategy enables
│   └── strategies/*.yaml      # per-strategy parameters + bounds
├── pmtrader/
│   ├── orchestrator.py        # async main loop, mode control, watchdog hooks
│   ├── datalayer/             # gamma.py, clob_rest.py, clob_ws.py, binance.py,
│   │                          # store.py (SQLite WAL), archive.py (raw JSON log)
│   ├── core/                  # models.py (Market, Book, Intent, Order, Fill),
│   │                          # fees.py, bankroll.py, clock.py
│   ├── strategies/            # base.py + s1_arb.py, s2_mm.py, s3_crypto.py, s4_calib.py
│   ├── allocator.py           # capital budgets, edge-decay detection
│   ├── risk.py                # the gate every intent passes through
│   ├── execution/             # live.py (py-clob-client), paper.py (fill simulator),
│   │                          # state_machine.py (order lifecycle + reconciliation)
│   ├── backtest/              # replay.py, costs.py, stats.py (bootstrap CIs, walk-forward)
│   └── api/                   # FastAPI app for dashboard (REST + WS push)
├── static/                    # dashboard HTML/JS/CSS + chat widget
├── scripts/                   # recon.py, fetch_history.py, run_backtest.py
└── tests/                     # pytest, full coverage of risk/fees/execution/strategies
```

**Core contract:** strategies emit `Intent` objects (side, token, price, size, time-in-force, *reasoning string*, expected edge after fees). They never touch the exchange. Flow: `Strategy → Allocator (budget check) → RiskManager (veto power) → Execution (live|paper) → Fill events → back to strategy + store`. Every intent, veto, order, fill, and reasoning line is persisted — the dashboard and all edge analysis read from that record.

**One strategy codebase, three modes:** backtest replays historical data through the same strategy classes; paper mode runs against the live order book with simulated fills; live mode signs real orders. Execution backends share one interface.

**Concurrency:** single asyncio process. WSS consumers feed an in-memory book cache; strategies are async tasks on tick/timer triggers; SQLite writes via a single writer task (WAL mode). A separate lightweight **watchdog process** (`watchdog.py`) launched by `start.bat` restarts the main process on crash/hang (heartbeat file) — on restart, execution reconciles open orders via REST before strategies resume. `cancel-all` is invoked on every shutdown path that can reach the API.

---

## 5. Strategies

### S1 — Structural Arb Scanner (riskless-class)
- **Binary pair:** if `ask(YES) + ask(NO) < 1 − fees − ε`, buy both; guaranteed $1 at resolution. Unwind early if the pair can be sold for `> entry + fees`.
- **Neg-risk multi-outcome:** if `Σ ask(YESᵢ)` across all mutually-exclusive outcomes `< 1 − fees − ε`, buy the set (exactly one resolves to $1). Mirror check on NO side.
- Hunts all active markets, prioritizes fee-free categories; ε covers partial-fill/legging risk; legging controls: fire both legs simultaneously, unwind immediately at marketable price if one leg fails (bounded loss accepted as cost of doing business, tracked).
- Capital recycles at resolution; sizing capped by book depth at the arb price.

### S2 — Market Maker (spread + rebates)
- Quote both sides around a reference price `r` = microprice (depth-weighted mid), spread `δ` set by recent realized volatility of `r` and book competition; inventory skew shifts quotes Avellaneda-Stoikov-style: `quote_mid = r − γ·inventory·σ²·τ`.
- **Adverse-selection monitor:** markout P&L (book mid at t+30s and t+5m after each fill, minus fill price). Rolling markout below threshold → widen, shrink size, or pull from that market. This is the self-defense mechanism that decides which markets are safe to make.
- Market selection (refreshed hourly): rebate-eligible, daily volume above floor, spread ≥ minimum viable, ≥48h to resolution (avoid resolution sniping), no scheduled binary catalyst (e.g., avoid quoting through a Fed decision in an economics market — catalyst calendar is config, not magic).
- Maker-only: never crosses the spread; orders priced to rest.

### S3 — Crypto Fair Value (model-driven taking)
- Targets BTC/ETH up/down and threshold markets (hourly→weekly). Fair value of "S_T > K": `P = Φ(ln(S/K) / (σ√τ))` (driftless lognormal), σ from EWMA realized vol on Binance 1m candles, with vol-of-vol guard widening the no-trade band when vol regime is unstable.
- Trade only when `|market_price − fair| > fees(p) + half_spread + margin`, where margin is a calibrated safety buffer. Crypto taker fees are the highest, so the bar is high — most hours produce no trade, by design.
- Prefers posting just inside the divergence (maker, no fee) over taking; takes only when divergence is large and decaying.
- Holds to resolution (short-dated); exits early if model and market re-converge profitably.

### S4 — Calibration Harvester (statistical bias)
- Built **only from backtest evidence**: fit calibration curves (resolved outcome rate vs. price) by category × price bucket × time-to-resolution on full Polymarket history; trade only buckets where the bias survives walk-forward splits and fees — expected v1 candidate: buying 93–98¢ near-resolution favorites where the historical hit rate clears price + fees.
- Strictly capped allocation (tail risk: rare favorite-losses are lumpy); per-event exposure cap is tightest here.
- If backtest shows no robust bucket, **S4 ships disabled** — absence of edge is a valid finding.

---

## 6. Allocator (the self-learning layer)

- Each strategy gets a capital budget = bankroll × weight. Weights update **weekly** from realized fee-adjusted performance: shrunken Sharpe-like score → softmax with floor 5% / cap 50%; shrinkage toward equal weight keeps early noise from whipsawing allocations.
- **Edge-decay detection:** rolling bootstrap 95% CI of per-trade EV per strategy. CI upper bound < 0 over the window, or drawdown > strategy-specific limit → strategy auto-demoted to paper; it must re-pass the statistical gate to regain capital. Promotions/demotions are logged with the evidence and shown on the dashboard.
- Parameter self-tuning happens **inside** strategies within pre-declared bounds from `config/strategies/*.yaml` (e.g., MM spread multiplier, S3 margin). The allocator never invents strategies; nothing self-modifies outside declared bounds.

## 7. Risk Manager (every intent passes; no exceptions)

| Rule | Default (config) |
|---|---|
| Fee-adjusted EV must be > 0, with stated reasoning | hard |
| Max exposure per market | 5% bankroll |
| Max exposure per event (correlated outcomes) | 10% |
| Max total capital at risk | 80% |
| Daily realized-loss halt | −10% → cancel all, halt, alert |
| Max order size vs. displayed book depth | ≤ 25% of depth at level |
| Price sanity | reject buys above model fair + buffer; reject orders in final pre-resolution window except S1 unwinds |
| Stale-data guard | book older than N sec → no new orders in that market |
| Sizing | fractional Kelly (¼-Kelly default) on per-trade edge estimate, capped by the limits above |

**Double-or-bust mode (D):** explicit run mode — start equity E₀, stop-and-celebrate at ≥ 2·E₀, orderly shutdown at ≤ 0.05·E₀ (a literal zero is unreachable gracefully; 5% floor preserves an audit trail and exit liquidity). Progress bar on dashboard. Kelly fractions and limits unchanged — the mode changes the *stopping rule*, not the risk discipline; gambling harder when behind is exactly the mistake the system exists to not make.

**Kill switches:** dashboard button (cancel-all + flatten-where-sane + halt); automatic on: repeated API failures, WSS silence > threshold, clock skew, daily-loss halt, equity floor.

## 8. Backtest & Statistical Methodology (anti-spuriousness)

- Data: full Polymarket prices-history + resolution outcomes for all resolvable markets (fetched by `fetch_history.py`, archived raw); Binance klines for S3.
- **Walk-forward:** parameters fit on window k, evaluated on window k+1, rolled. No strategy sees its evaluation data during fitting. Strategy logic and parameter grids are pre-specified in this spec's companion config — no post-hoc strategy invention from the same data.
- **Costs modeled conservatively:** taker fees at category rate, fills assume crossing the full spread, plus slippage haircut; maker fills require price to trade *through* the quote (touch ≠ fill), rebates credited at published rates only for eligible markets.
- **Output:** per-strategy equity curves, per-trade EV bootstrap 95% CI, max drawdown, exposure stats. **Go/no-go rule: validation-period EV CI lower bound > 0 after costs**, else the strategy ships disabled.
- Known honesty limits (documented, not hidden): historical books are not fully reconstructable (prices-history is sampled mids), so backtest fills for S1/S2 are approximations — which is exactly why the **paper gate** exists: ≥ 200 paper trades *and* bootstrap 95% CI of per-trade EV > 0 *and* ≥ 7 calendar days, per strategy, before live capital. S2 (whose edge is microstructural) leans on the paper gate hardest; its backtest is treated as smoke test only.

## 9. Dashboard

FastAPI + vanilla HTML/JS (workspace house style), WebSocket push, chat widget per workspace rule. Panels: equity curve (live vs. paper distinguished); double-or-bust progress; positions & working orders; per-strategy P&L, allocation weight, gate status (backtest/paper/live) with CIs; decision log (every intent with reasoning, vetoes with the rule that fired); risk panel (limit utilizations, halts); controls (mode switch, per-strategy enable, kill switch). Read-only over LAN; controls require a config-set token.

## 10. Testing

- TDD throughout (workspace rule: tests alongside code). pytest + pytest-asyncio.
- **100% branch coverage required on:** `risk.py`, `fees.py`, `execution/state_machine.py`, `bankroll.py` — the money-losing-bug surfaces.
- Strategy tests use golden order-book fixtures (recorded real books) asserting exact intents.
- Backtest determinism test: same inputs → bit-identical results.
- Paper-fill simulator validated against recorded live trade tapes (would-have-filled vs. actually-traded).
- Integration test: full loop in paper mode against recorded WSS replay, end-to-end through dashboard API.
- `scripts/recon.py` doubles as a live smoke test of API assumptions; security-audit skill before any live-money enablement.

## 11. Build Order

0. **Recon** — verify every API assumption empirically; document depth/limits of prices-history.
1. **Core + data layer** — models, fees, SQLite store, Gamma/CLOB REST clients, history fetcher.
2. **Backtest harness + stats** — replay, cost model, bootstrap/walk-forward machinery.
3. **S1 + S4 research** — run them through backtest (they need only REST data); S4 go/no-go decided here.
4. **Execution + risk + paper simulator** — order state machine, risk gate, WSS live feeds.
5. **S2 + S3** — need live books; develop directly in paper mode.
6. **Allocator + orchestrator + watchdog** — the autonomous loop.
7. **Dashboard.**
8. **Paper-mode burn-in** — the statistical gate runs; live enablement is a config flip the user makes after gates pass + security audit.

---

*Spec self-review completed 2026-06-09: no placeholders; scope is large but phased with each build-order step independently testable; ambiguities resolved by delegated decisions marked (D). The single highest-risk assumption — historical data depth for backtesting — is addressed first by Phase 0 recon.*
