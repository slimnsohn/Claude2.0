# Data Specification — Partial-Game Pricing Model

Spec for checking data availability against The Odds API (or any odds data provider).

---

## Sports & Leagues

- **NBA** (regular season + playoffs)
- **NFL** (regular season + playoffs)
- Optional: NCAAB, NCAAF (same model framework applies)

## Time Range

- **Minimum useful:** 3 most recent completed seasons
- **Ideal:** 5+ seasons for both sports
- **Goal:** ability to refit model annually with rolling window

---

## Dataset 1 — Full-Game Closing Lines (MUST HAVE)

Per game, the **closing** values (the line at the moment before tipoff/kickoff) from a sharp book — Pinnacle preferred, Circa or Bookmaker.eu acceptable:

| Field | Type | Notes |
|---|---|---|
| game_id | string | unique identifier |
| game_date | date | |
| sport | enum | NBA / NFL |
| home_team | string | |
| away_team | string | |
| closing_spread | float | signed; document convention (e.g., negative = home favored) |
| closing_total | float | |
| closing_ml_home | int | American odds |
| closing_ml_away | int | American odds |
| sportsbook | string | which book this close came from |
| season | int | |
| season_type | enum | regular / playoff |

---

## Dataset 2 — Segment Closing Lines (THE HOLY GRAIL)

Same as Dataset 1 but for **partial-game markets at close**, again from a sharp book. This is what lets you fit "what sharp books think" rather than "what reality is":

| Field | Type | Notes |
|---|---|---|
| game_id | string | foreign key to Dataset 1 |
| segment | enum | Q1, Q2, Q3, Q4, H1, H2 |
| closing_spread | float | |
| closing_total | float | |
| closing_ml_fav | int | |
| closing_ml_dog | int | |
| sportsbook | string | |

If multiple books are available (e.g., Pinnacle AND DraftKings) for the same game-segment, grab both — comparing sharp vs. soft for the same proposition is direct evidence of mispricing.

---

## Dataset 3 — Game Outcomes (MUST HAVE)

Per game, end-of-quarter and end-of-half scores:

| Field | Type | Notes |
|---|---|---|
| game_id | string | |
| home_q1, home_q2, home_q3, home_q4 | int | points scored in quarter (NOT cumulative) |
| away_q1, away_q2, away_q3, away_q4 | int | |
| home_ot, away_ot | int | total OT points if applicable |
| went_to_ot | bool | |
| home_final, away_final | int | including OT |

Most APIs only give cumulative or final scores; per-quarter may need to be derived from cumulative.

---

## Dataset 4 — Live/Historical Line Movement (NICE TO HAVE)

Per game, the line at multiple snapshots (opening, 24h-before, 1h-before, close):

| Field | Type | Notes |
|---|---|---|
| game_id | string | |
| timestamp | datetime | when the snapshot was taken |
| market | enum | full-game / Q1 / H1 / etc. |
| line_type | enum | spread / total / ml |
| value | float | |
| price_a, price_b | int | American odds on each side |
| sportsbook | string | |

This enables "did the Q1 line move correctly when the full-game line moved?" detection — the actual live exploit.

---

## Specific Questions to Ask The Odds API Docs

1. **Do they offer historical odds, or only live?** The free/cheap tier is usually live-only. Historical is a separate paid product, often pricey.
2. **What sportsbooks are covered for historical?** You want Pinnacle ideally; DraftKings/FanDuel/BetMGM at minimum.
3. **What markets beyond `h2h`, `spreads`, `totals`?** You specifically need `quarter_spreads`, `quarter_totals`, `quarter_h2h`, `h1_spreads`, `h1_totals`, `h1_h2h` (and second-half versions).
4. **What snapshot granularity for historical?** Closing-line-only, or multiple snapshots? Closing is sufficient for model fitting; intraday snapshots are needed for backtesting live exploitation.
5. **Rate limits and pricing per call?** Historical pulls of 5 seasons × 1,000+ NBA games × 6 segments × 3+ books = a lot of API calls.
6. **Do they provide game scores including quarter-by-quarter?** If yes, that's Datasets 3 and possibly 1/2 in one place.

---

## What Each Dataset Unlocks

| Dataset | Unlocks |
|---|---|
| 1 (full-game closes) | Refit spread/total/σ weights with proper closing totals (currently NBA uses realized totals — has look-ahead bias) |
| 2 (segment closes) | **The actual edge model.** Fit `w^μ_book = posted_quarter / posted_full` per book per spread bucket. Identify which books are systematically off |
| 3 (quarter scores) | Already have this for both sports; no current gap |
| 4 (line movement) | Backtest "when full-game line moves X, by what does each book move Q1?" — quantifies the lag exploit |

---

## TL;DR Query for Claude Code

> "Check if The Odds API provides: (a) historical closing odds for NBA and NFL, going back 3+ seasons, (b) markets for quarter and half spreads/totals/moneylines specifically (not just full-game), (c) odds from Pinnacle or another sharp book vs. DraftKings/FanDuel/BetMGM, and (d) end-of-quarter scores. Report exact endpoint names, market codes, historical coverage depth in years, sportsbook list, and pricing tier required for each."

---

## Priority Order

If budget is constrained, acquire in this order:

1. **Dataset 1** (full-game closing lines, especially NBA closing totals) — fixes the look-ahead bias in the current model. Cheapest, highest impact.
2. **Dataset 3** (quarter scores) if not already aligned with Dataset 1's game IDs.
3. **Dataset 2** (segment closing lines, ideally for both Pinnacle AND a soft book) — this is what enables the actual edge identification. Most expensive but transformative.
4. **Dataset 4** (line movement snapshots) — required only if pursuing live/intraday exploitation. Skip if pre-game model is the focus.
