# TODO — polymarket-trader

> Update manually. This file persists across sessions.

## Now

- [ ] Paper-mode burn-in: run via start.bat, watch the dashboard gates
      (need ≥200 paper trades + positive CI + ≥7 days per strategy)

## Next

- [ ] Review paper results; flip live only after gates pass + security audit
- [ ] Up/down period markets for S3 (needs period-open price tracker)
- [ ] Live-mode positions reconcile via data-api on startup

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
