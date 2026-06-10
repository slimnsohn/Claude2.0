# TODO — polymarket-trader

> Update manually. This file persists across sessions.

## Now

- [ ] Paper-mode burn-in: run via start.bat, watch the dashboard gates
      (need ≥200 paper trades + positive CI + ≥7 days per strategy)

## Next

- [ ] Review paper results; flip live only after gates pass + security audit
- [ ] Wire S1's neg-risk set arb: orchestrator never calls on_event, so only
      binary-pair arbs run today (needs gamma.events() + event book routing)
- [ ] Up/down period markets for S3 (needs period-open price tracker)
- [ ] Live-mode positions reconcile via data-api on startup (startup now
      expires orphaned DB orders + cancel-all on exchange; full fill-recovery
      via data-api still missing)

## Review notes (2026-06-10 bug sweep — fixed)

- Paper maker fills now require a strict trade-through (was at-price; inflated
  paper stats that feed the live gate)
- S1/S4 intents now carry event_id (the 10%-per-event cap was silently skipped)
- Risk vetoes entry intents missing condition_id (cap-bypass hardening)
- Startup reconcile expires orphaned orders from prior runs
- Dashboard resume refuses to override a double-or-bust verdict (409)
- One strategy raising no longer stalls the tick loop (isolated + logged)
- S2: inventory skew clamped to max_spread/2; per-quote notional capped at
  $40 so the 5%-per-market risk cap can approve quotes on a $1k bankroll

## Review notes (deferred, by design for now)

- Allocator edge-decay check needs >=30 live trades before it can demote; a
  strategy promoted then barely trading stays LIVE_ELIGIBLE on paper evidence
- Gated strategies may still SELL (unwind) in live mode — intended, documented
- SQLite writes are synchronous on the event loop (~1ms WAL commits; fine at
  current intent rates, revisit if tracked markets grow 10x)

## Backlog

- [ ] Maker rebate accrual tracking (currently treated as bonus, not EV)
- [ ] Cross-platform arb (Kalshi)
- [ ] CTF split/merge for true riskless pair redemption pre-resolution
- [ ] VPS deployment notes

## Done

- [x] Spec + plan (2026-06-09)
- [x] API recon: all 8 probes pass; per-market feeSchedule discovered
- [x] Core: models, fees, store, clients, history fetcher (resumable)
- [x] Backtest harness + bootstrap/walk-forward stats
- [x] S1 arb, S2 MM (two-sided binary quoting), S3 crypto FV, S4 calibration
- [x] Calibration research on 1,976 resolved markets -> 1 qualified bucket
- [x] Risk manager + bankroll + order state machine (100% branch coverage)
- [x] Paper + live execution, group-unwind router, WSS feeds
- [x] Allocator with edge-decay demotion + paper gate
- [x] Orchestrator + watchdog + live-arming interlock
- [x] Dashboard (equity, gates, decision log, kill switch)
- [x] 283 tests passing, e2e integration on recorded real WSS tape
