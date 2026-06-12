# Polymarket Autonomous Trader

Multi-strategy autonomous trading system for Polymarket (international .com).
Four strategies over shared infrastructure, a self-learning capital allocator,
hard risk limits, and a statistical gate between paper and live trading.

**Default state is paper mode. It cannot spend real money until you complete
the arming steps below — and it should not, until the gates pass.**

## Quick start

```
start.bat        # installs deps if needed, starts watchdog + trader, opens dashboard
```

Dashboard: http://127.0.0.1:8765 — equity curve, double-or-bust progress,
positions, working orders, per-strategy allocation & gate status, and the
decision log (every intent, approval, and veto, with reasoning).

Tests: `.venv\Scripts\python -m pytest` (283 tests; risk/fees/bankroll/order
state machine are at 100% branch coverage).

## The four strategies

| | Edge source | Gate evidence |
|---|---|---|
| S1 arb | YES+NO ask sum < $1; neg-risk sets < $1 (riskless class) | structural math + paper fills |
| S2 market maker | spread capture + maker rebates, markout self-defense | paper gate only (microstructure can't be backtested honestly) |
| S3 crypto fair value | binary-option pricing of BTC/ETH markets vs Coinbase spot/vol | backtest + paper gate |
| S4 calibration | favorite-longshot bias from 1,976 resolved markets; 1 bucket passed walk-forward (d6/30d+, net +8.7c/share) | `data/calibration_report.json` |

The **allocator** reweights capital weekly toward strategies with proven
fee-adjusted edge (shrunk-Sharpe softmax, 5%–50% bounds) and demotes any
strategy whose rolling 95% CI of per-trade EV drops below zero back to paper.

**Paper → live gate (per strategy):** ≥200 paper trades AND bootstrap 95% CI
of per-trade EV > 0 AND ≥7 days of history. The dashboard shows gate status.

## Risk rules (always on, see `pmtrader/risk.py`)

Fee-adjusted EV > 0 · ≤5% equity per market · ≤10% per event · ≤80% total at
risk · daily loss −10% → halt · ≤25% of displayed depth · no stale books ·
no entries in the final 10 min before resolution · quarter-Kelly sizing.
**Double-or-bust mode** stops the run at 2× equity (won) or 5% (lost); it
changes the stopping rule, never the sizing.

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
   execution. S2/S3 are excluded (can't be replayed honestly from sampled
   mids) and keep the full 200-trade / 7-day gate.
4. `python scripts/run_execution_report.py` — what paper trading is for:
   maker fill rate, time-to-fill, taker price improvement vs the cost
   model's assumptions. Accumulates across reboots.

Gate evidence is rebuilt from SQLite on every startup
(`Orchestrator.refresh_allocator_trades`), so reboots cost nothing but the
minutes offline. Dashboard: `/api/walkforward`, `/api/execution`, and a
Backtest column in the strategies panel.

## Going live (the two-key interlock)

1. Pass the paper gate (dashboard shows LIVE_ELIGIBLE per strategy).
2. Run the security audit skill against this project.
3. Export your wallet key from Polymarket settings (email-login accounts:
   Settings → Export Private Key). **Treat it like cash.**
4. Set Windows env vars (never in any file):
   `POLYMARKET_PRIVATE_KEY`, `POLYMARKET_FUNDER_ADDRESS` (your deposit/proxy
   address), `POLYMARKET_SIGNATURE_TYPE` (1 = email/Magic login, 0 = browser
   wallet, 2 = safe).
5. In `config/settings.yaml`: `mode: live` **and** `live_armed: true`.
   Anything less refuses to start. Fund the account with the bankroll amount.

## Operations

- **Watchdog:** `start.bat` runs `watchdog.py`, which restarts the trader on
  crash or stale heartbeat (max 5/hour, then it stops and asks for a human).
  On startup the trader reconciles open orders against the exchange before
  strategies resume. Every shutdown path cancels all orders.
- **Kill switch:** dashboard button (needs the control token from
  `config/settings.yaml`) — cancels everything and halts. Resume from the
  same place.
- **Data refresh:** `scripts/fetch_history.py` (resumable) pulls market
  history; `scripts/run_calibration_research.py` re-derives the S4 whitelist;
  `scripts/recon.py` re-verifies every API assumption.

## Known limitations (honest list)

- Backtests use sampled mids with a conservative cost model — S1/S2 edges are
  judged by the paper gate, not the backtest.
- Historical data for resolved markets only covers early market life (API
  limitation), so near-resolution calibration effects are paper-gate-only.
- S4's qualified bucket was measured in a fee-free era; live fees are charged
  per today's schedule at EV-check time (handled, but shrinks the edge).
- Live-mode position reconciliation trusts the user WSS channel + REST
  reconcile; a long offline gap may need a restart to resync.
- Maker rebates are earned but not modeled in EV (treated as bonus).

## Architecture

`pmtrader/` — `datalayer/` (Gamma, CLOB REST/WSS, Coinbase, SQLite store,
raw archive) · `strategies/` (S1–S4 + base) · `risk.py` · `allocator.py` ·
`execution/` (paper + live backends, order state machine, group router) ·
`backtest/` (replay, costs, bootstrap/walk-forward stats) · `orchestrator.py`
· `api/` (dashboard). Spec: `docs/superpowers/specs/2026-06-09-polymarket-trader-design.md`.
