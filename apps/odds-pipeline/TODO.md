# TODO — odds-pipeline

## Now
- [ ] Find NFL per-quarter score source. `nfl_data_py.import_schedules` only exposes
  full-game scores — no `home_score_q1..q4` columns. Options: ESPN scoreboard JSON
  (same pattern as NCAAB adapter) or `nfl_data_py.import_pbp_data` aggregated by `qtr`.
- [ ] Find NBA scores workaround. `nba_api` BoxScoreSummaryV2 times out against
  stats.nba.com from this network. Need User-Agent headers or alternate source
  (basketball-reference, ESPN). Live run captured 0 NBA scores.
- [ ] Resolve NCAAF cross-source identity: odds returns full names ("OHIO STATE
  BUCKEYES"); CFBD uses similar but slightly different ("Ohio State"). Need to add
  `identity/aliases/NCAAF.json` once we have a CFBD_API_KEY and can pull real
  results. Bowl/CFP games use the team's full Bowl Subdivision name, not nickname.
- [ ] Add `CFBD_API_KEY` to env to pull NCAAF scores. Free key at
  https://collegefootballdata.com/key.

## Findings from 2026-05-25 sample run (NBA+NFL+NHL+NCAAF, Jan 2025, limit 3)
- **Per-event historical cost: 10× per market per region** (NOT 1× as docs hinted).
  One NBA game (7 markets × 2 regions) = 141 credits. Budget accordingly.
- **Pinnacle DOES return segment markets** — `spreads_q1`, `totals_q1`, `spreads_h1`,
  `totals_h1` all present for NBA. This is the sharp-vs-soft data the model needs.
- **DraftKings does NOT carry segment markets** in The Odds API historical responses
  — only `h2h`/`spreads`/`totals`. Use FanDuel, BetMGM, Caesars, BetRivers, Bovada,
  BetOnline.ag, or BetUS as the "soft" comparison against Pinnacle's segment lines.
- **NHL `spreads_p1` / `totals_p1` are valid market keys** — 3 NHL games pulled
  successfully with these keys. Period-1 lines confirmed available.
- **Bookmaker variance per game ranges ~14-25 books** (NBA had ~25 bookmakers in
  one response; many are EU shops carrying only h2h).
- **Real Odds API per-event historical envelope wraps the event** in
  `{timestamp, previous_timestamp, next_timestamp, data: {event...}}`. The plan's
  synthetic fixture used the unwrapped event directly — derive.py now handles both.
- **Sample run totals:** 12 odds-pulls archived (4 sports × 3), ~265 unique games
  in DB after join, ~2,300 odds rows, ~252 score rows, ~1,560 credits spent.

## Next
- [ ] Forward-collection cron via Windows Task Scheduler (calls pull-odds with live
  /odds endpoint daily, just before tipoff/kickoff per sport)
- [ ] Replace synthetic test fixtures with real-capture fixtures now that we have
  a working pull
- [ ] Cross-source date matching: 1 NFL game (`CIN@PIT`) mismatched because odds had
  it 2025-01-05 UTC and nfl_data_py had it 2025-01-04 local. Either normalize both
  sides to a consistent timezone before `build_game_id`, or use the matcher's
  ±1-day tolerance during derive (currently bypassed since derive joins by exact
  game_id PK).

## Backlog
- Multi-snapshot ingestion (opening, 24h, 1h, close per game) — schema already supports it
- Alt-line markets (`is_alternate` flag on odds_snapshots)
- Player props ingestion (separate pipeline)
- Sharp-book alternative if a Pinnacle-equivalent emerges (Circa, Bookmaker.eu not in The Odds API)

## Done
- 2026-05-24: v1 framework — 17 tasks, 48 tests, 6 sport adapters, hybrid raw+SQLite, ingest+derive pipeline.
- 2026-05-25: Live sample run validated end-to-end. Findings documented above. NFL adapter corrected (FULL only), envelope-unwrap fix in derive, NFL+NHL aliases populated for 32+32 teams.
