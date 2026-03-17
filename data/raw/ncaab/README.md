# NCAA Basketball Odds & Scores Dataset

Historical NCAA men's basketball game results with betting odds, covering **18 seasons** (2007-08 through 2024-25).

## Files

| File | Rows | Description |
|------|------|-------------|
| `unified_ncaa.csv` | ~62,800 | Cleaned, unified dataset with scores, moneylines, spreads, totals, and game classification. **Start here.** |
| `ncaa_games_classified.csv` | ~62,600 | Intermediate version with rotation numbers and date formatting. Similar data, slightly different schema. |
| `raw/*.xlsx` | 15 files | Original source spreadsheets (2007-08 through 2021-22). Seasons after 2022 were added from other sources. |
| `ncaa_tournament_seeds.json` | ~1,088 | All 64 teams + seeds + regions for every NCAA tournament 2008-2025 (excl. 2020). |

## Schema — `unified_ncaa.csv`

| Column | Type | Description |
|--------|------|-------------|
| `game_date` | date | Game date (YYYY-MM-DD) |
| `season_end_year` | int | Calendar year the season ends (e.g. 2025 = 2024-25 season) |
| `game_type` | str | `regular_season`, `conference_tournament`, `ncaa_tournament`, `nit` |
| `round` | str | Tournament round when applicable: `R64`, `R32`, `S16`, `E8`, `F4`, `FF`, `CHAMP` |
| `away_team` / `home_team` | str | Team identifiers (compact format, e.g. `MemphisU`, `GardnerWebb`) |
| `neutral_site` | bool | Whether the game was at a neutral venue |
| `away_half1` / `away_half2` / `away_final` | float | Away team halftime, second half, and final scores |
| `home_half1` / `home_half2` / `home_final` | float | Home team halftime, second half, and final scores |
| `away_ml` / `home_ml` | str | American moneylines (`NL` when not listed) |
| `open_line` / `close_line` | float | Opening and closing point spreads (positive = home favored, acts as total in some contexts) |
| `odds_source` | str | Source of odds data: `SBR`, `Pinnacle/FanDuel`, `Pinnacle/Pinnacle` |
| `away_team_display` / `home_team_display` | str | Human-readable team names |

## Coverage

- **Seasons:** 2007-08 through 2024-25
- **Game types:** Regular season, conference tournaments, NCAA tournament (with round labels), NIT
- **Odds data:** Moneylines, opening/closing spreads. Source shifts from SBR (older) to Pinnacle/FanDuel (newer).
- **Scores:** Final scores plus halftime splits

## Usage Notes

- Moneyline values of `NL` mean no line was available — filter or handle as null.
- Team identifiers are compact strings without spaces. Use `*_display` columns for readable names.
- `open_line` / `close_line` can represent spreads or totals depending on context and season — verify against scores when building models.
- Raw `.xlsx` files cover through 2021-22. Data after that was sourced and appended separately.

## Schema — `ncaa_tournament_seeds.json`

Array of objects with:

| Field | Type | Description |
|-------|------|-------------|
| `year` | int | Tournament year (season end year) |
| `region` | str | Bracket region (East, West, South, Midwest, etc.) |
| `seed` | int | Seed number (1-16) |
| `team` | str | Human-readable team name |

Coverage: 2008-2025 (17 tournaments, excl. 2020 COVID cancellation). 64 teams per year.

## Pipelines

| Pipeline | Location | Output |
|----------|----------|--------|
| `build_11_15_seeds.py` | `../../_pipelines/sports/` | Joins seeds with game data to produce `apps/ncaa_11_15_seeds/data/results.json` |

## Good For

- Spread/total modeling and backtesting
- Moneyline value analysis
- Tournament performance research (seeds, upsets, round-by-round)
- Historical trends by team, conference, or venue type
- Line movement analysis (open vs. close)
