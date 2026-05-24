# TODO — odds-pipeline

## Now
- [ ] Live sample run (needs THE_ODDS_API_KEY + CFBD_API_KEY in env):
  ```
  cd apps/odds-pipeline
  python -m odds_pipeline init
  python -m odds_pipeline pull-odds --sport NBA,NFL,NHL,NCAAF --from 2025-01-01 --to 2025-01-31 --limit 10
  python -m odds_pipeline pull-results --sport NBA,NFL,NHL,NCAAF --from 2025-01-01 --to 2025-01-31
  python -m odds_pipeline build
  python -m odds_pipeline status
  ```
- [ ] After sample run, resolve spec open questions and document findings here:
  - Per-event historical credit cost: 1× or 10× per market/region?
  - Did Pinnacle return segment markets (spreads_q1, totals_h1)?
  - Are NHL `spreads_p1`/`totals_p1` the correct market keys?
  - Are MLB `spreads_1st_5_innings`/`totals_1st_5_innings` correct?
  - List of unmatched team-name aliases per sport (add to `odds_pipeline/identity/aliases/{sport}.json`, re-run `build`)

## Next
- [ ] Forward-collection cron via Windows Task Scheduler (calls pull-odds with live /odds endpoint daily)
- [ ] Replace synthetic fixtures with real API captures (tests/fixtures/) — currently shapes are documented from the API docs, not captured from live calls

## Backlog
- Multi-snapshot ingestion (opening, 24h, 1h, close per game)
- Alt-line markets (`is_alternate` flag on odds_snapshots)
- Player props ingestion (separate pipeline)
- Sharp-book alternative if a Pinnacle-equivalent emerges

## Done
- 2026-05-24: v1 framework complete — 17 tasks, 48 tests passing, 6 sport adapters, hybrid raw+SQLite storage, full ingest+derive pipeline. Live sample-run deferred (needs API key).
