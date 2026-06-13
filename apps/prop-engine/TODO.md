# TODO — Prop Engine

> Update manually. This file persists across sessions.

## Now
- [ ] Provide `ODDS_API_KEY` env var (paid Odds API tier)
- [ ] Edit `config/user.json` with your bankroll
- [ ] First live slate test

## Next
- [ ] Settle and log first batch of bets to validate ROI tracking
- [ ] After 50+ logged plays, run `scripts/calibration.py` to inspect reliability
- [ ] Wire real `stats.wnba.com` feature lookup in `cli.run_wnba()` (currently placeholder position/avg/sigma)

## Backlog
- [ ] v1.5: NoVig + ProphetX + Kalshi direct API ingestion
- [ ] v2: Negative Binomial per stat type
- [ ] v2: EWMA features tuned per-stat
- [ ] v2: Pace + opp positional defense residuals
- [ ] v2: LLM news classifier + bet thesis generator
- [ ] NBA / MLB plugins under `sports/`

## Done
- [ ] v1 framework scaffolded
