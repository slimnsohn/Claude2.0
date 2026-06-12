# Free & Public APIs for WNBA Player Stats: A Builder's Guide for a Player‑Prop Projection Model

**TL;DR**
- The best free stack for a WNBA player‑prop model is a **three‑layer pull**: (1) **ESPN's undocumented `site.api.espn.com` / `site.web.api.espn.com` endpoints** for daily scoreboards, game IDs and per‑game player box scores (no key, no auth), (2) **`stats.wnba.com`** (NBA Stats infrastructure with `LeagueID=10`) for full historical `PlayerGameLog`/`LeagueGameLog` with PTS, REB, AST, STL, BLK, FG3M, TOV, MIN (no key, but you MUST send specific browser headers — `x-nba-stats-origin`, `x-nba-stats-token`, `Referer`), and (3) **SportsDataverse GitHub release artifacts** (`sportsdataverse-data` repo) for free, pre‑built season‑by‑season WNBA player box‑score files back to 2002.
- **BallDontLie's WNBA API does cover WNBA, but the actual per‑game player‑stats endpoint (`/wnba/v1/player_stats`) is gated to the paid GOAT tier ($39.99/mo)** — the free tier only exposes Teams, Players and Games (per the wnba.balldontlie.io Account Tiers table; Active Players, Injuries, Standings and Play‑by‑Play require ALL‑STAR at $9.99/mo, and the free plan is hard‑capped at 5 requests/min). Do not assume "free" BallDontLie gives you the box scores you need; it does not.
- For Python wrappers: **`wehoop-py`** and **`sportsdataverse-py`** (SportsDataverse) are the closest equivalents to `nba_api` for the WNBA; **`swar/nba_api`** itself exposes `players.get_wnba_players()` and accepts `LeagueID='10'`, and there is a dedicated **`rozzac90/wnba`** wrapper. Pair stats.wnba.com / ESPN scrapes with **The Odds API's `/v4/sports/basketball_wnba/events/{eventId}/odds`** (markets `player_points`, `player_rebounds`, `player_assists`, `player_threes`, plus `*_alternate` for X+ milestones) to compare your projections to live lines.

## Key Findings

1. **ESPN hidden endpoints are the easiest free source.** No API key, no auth, JSON over HTTPS, CORS open enough that browser clients work (no `Access-Control-Allow-Origin` issues from `site.api.espn.com`). The `/scoreboard`, `/teams`, and crucially `/summary?event=…` routes return per‑game player box scores including points, rebounds, assists, steals, blocks, threes and turnovers. No documented hard rate limit, but community guidance is "be respectful — implement caching" and avoid hammering. ESPN can and does change paths without notice.

2. **`stats.wnba.com` is the same API server as `stats.nba.com`, just with `LeagueID=10`.** Every endpoint under `stats.nba.com/stats/...` (PlayerGameLog, LeagueGameLog, BoxScoreTraditionalV2/V3, PlayerCareerStats, PlayerDashboardByGameSplits, PlayerDashboardByLastNGames, LeagueDashPlayerStats, etc.) works under `stats.wnba.com/stats/...` when you pass `LeagueID=10`. Returned fields for player game log are exactly: `SEASON_ID, Player_ID, Game_ID, GAME_DATE, MATCHUP, WL, MIN, FGM, FGA, FG_PCT, FG3M, FG3A, FG3_PCT, FTM, FTA, FT_PCT, OREB, DREB, REB, AST, STL, BLK, TOV, PF, PTS, PLUS_MINUS, VIDEO_AVAILABLE` — i.e., everything a prop model needs. The cost is operational: the server is behind Cloudflare and will return 403/429 unless you send a realistic browser User‑Agent plus `x-nba-stats-origin: stats`, `x-nba-stats-token: true`, and `Referer: https://stats.wnba.com/` (or `https://www.wnba.com/`).

3. **BallDontLie has a real WNBA API but you cannot get per‑game stats on the free plan.** The endpoint is documented at `https://wnba.balldontlie.io/` and returns clean JSON (`min, fgm, fga, fg3m, fg3a, ftm, fta, oreb, dreb, reb, ast, stl, blk, turnover, pf, pts, plus_minus`) with data back to 2008. But the tier matrix is unambiguous: Player Stats, Team Stats, Player Season Stats, Team Season Stats, Betting Odds and Player Props are **GOAT‑tier only** ($39.99/mo for WNBA alone, or $299.99/mo ALL‑ACCESS). Free tier gets you Teams, Players, and Games (schedule/score) — useful as a player‑ID lookup table but not a substitute for stats.wnba.com or ESPN for the actual stat lines.

4. **For Python, three packages give first‑class WNBA support without an API key:** `wehoop-py` (Saiem Gilani / SportsDataverse), `sportsdataverse-py`, and `swar/nba_api` (which exposes `players.get_wnba_players()` and accepts `league_id='10'`; under the hood you may want to override the host to `stats.wnba.com`). A dedicated lightweight wrapper `rozzac90/wnba` also exists. Both `nba_api` and `py_ball` (`basketballrelativity/py_ball`) document `league_id = '10'` explicitly as WNBA.

5. **Free bulk historical data via SportsDataverse GitHub Releases.** The R wrappers (`wehoop`) and Python wrapper (`sportsdataverse.wnba`) point to release‑hosted files. The URL pattern is `https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_wnba_player_boxscores/player_box_{YEAR}.rds` (with parallel `espn_wnba_team_boxscores`, `espn_wnba_pbp`, `espn_wnba_schedules` tags). The Python `sportsdataverse.wnba.load_wnba_player_boxscore(seasons=range(2002, 2026))` call returns a polars or pandas DataFrame directly — this is the single fastest way to backfill multi‑season game logs for model training, with no scraping at all. Coverage starts in 2002.

## Details

### 1) ESPN hidden API (`site.api.espn.com`, `site.web.api.espn.com`)

Pricing: **free, no key, no auth, no signup.** Unofficial; can break without notice. Production caveat: front it with caching.

Core WNBA endpoints (confirmed working pattern — substitute `nba` → `wnba` from the documented gist):

| Purpose | URL |
|---|---|
| Today's scoreboard | `https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard` |
| Scoreboard for a date | `https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard?dates=20250715` |
| Scoreboard for a date range | `…/scoreboard?dates=20250701-20250731` |
| All teams | `https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/teams` |
| Team detail | `https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/teams/{team}` |
| News | `https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/news` |
| **Game summary (box score + plays + odds)** | `https://site.web.api.espn.com/apis/site/v2/sports/basketball/wnba/summary?event={eventId}` |
| Athletes (roster) | `https://sports.core.api.espn.com/v2/sports/basketball/leagues/wnba/seasons/{YEAR}/teams/{TEAM_ID}/athletes?limit=200` |
| Player events / game log | `https://sports.core.api.espn.com/v2/sports/basketball/leagues/wnba/athletes/{athleteId}/eventlog?season={YEAR}` |

The **summary** endpoint is the key one for prop building. Its `boxscore.players[].statistics[].athletes[].stats` array contains, in standard ESPN basketball order: MIN, FG (M‑A), 3PT (M‑A), FT (M‑A), OREB, DREB, REB, AST, STL, BLK, TO, PF, +/-, PTS. You get game IDs from the scoreboard call (`events[].id`), then iterate `/summary?event=…` to harvest player rows.

Rate limits: no published number. Community consensus is to cache aggressively and stay under a few requests per minute per game. CORS: requests from browsers work directly — `site.api.espn.com` returns permissive headers; you do **not** need a proxy for client‑side dashboards (though for a betting model you'll want server‑side calls so you can cache).

### 2) `stats.wnba.com` (the official WNBA Stats API)

**This is the richest free WNBA source.** It is the same Cloudflare‑fronted API that powers stats.nba.com — same endpoints, same JSON shape — and it requires no API key. What it *does* require: the exact headers below, or Cloudflare returns 403 / hangs.

Required request headers (the canonical wehoop / nba_api set):
```
User-Agent: Mozilla/5.0 (...)  # any realistic desktop UA
Accept: application/json, text/plain, */*
Referer: https://www.wnba.com/         (or https://stats.wnba.com/)
Origin: https://www.wnba.com
x-nba-stats-origin: stats
x-nba-stats-token: true
Host: stats.wnba.com
Connection: keep-alive
```

CORS: `stats.wnba.com` does **not** send permissive CORS headers, so direct browser fetches from your own origin will fail — you must proxy through a server.

The most useful endpoints for a prop model (all accept `LeagueID=10`):

| Endpoint | Example URL |
|---|---|
| Player game log (single player, all games this season) | `https://stats.wnba.com/stats/playergamelog?DateFrom=&DateTo=&LeagueID=10&PlayerID=1628932&Season=2025&SeasonType=Regular+Season` |
| League‑wide game log (every player‑game in the season) | `https://stats.wnba.com/stats/leaguegamelog?Counter=1000&Direction=DESC&LeagueID=10&PlayerOrTeam=P&Season=2025&SeasonType=Regular+Season&Sorter=DATE` |
| Boxscore (traditional V2 per game) | `https://stats.wnba.com/stats/boxscoretraditionalv2?GameID=1022500001&StartPeriod=1&EndPeriod=10&StartRange=0&EndRange=55800&RangeType=2` |
| Boxscore advanced | `https://stats.wnba.com/stats/boxscoreadvancedv2?GameID=…` |
| Player dashboard – last N games | `https://stats.wnba.com/stats/playerdashboardbylastngames?PlayerID=1628932&LeagueID=10&Season=2025&SeasonType=Regular+Season&MeasureType=Base&PerMode=PerGame&...` |
| Player dashboard – by opponent / by splits | `playerdashboardbyopponent`, `playerdashboardbygamesplits`, `playerdashboardbygeneralsplits` (same pattern) |
| League dash – all players, totals | `https://stats.wnba.com/stats/leaguedashplayerstats?LeagueID=10&Season=2025&SeasonType=Regular+Season&PerMode=PerGame&MeasureType=Base&...` |
| Common all players (roster lookup) | `https://stats.wnba.com/stats/commonallplayers?LeagueID=10&Season=2025&IsOnlyCurrentSeason=1` |
| Common player info | `https://stats.wnba.com/stats/commonplayerinfo?PlayerID=1628932&LeagueID=10` |
| Play‑by‑play | `https://stats.wnba.com/stats/playbyplayv2?GameID=1022500001&StartPeriod=1&EndPeriod=10` |

Fields returned by `playergamelog` (canonical for prop modeling): `SEASON_ID, Player_ID, Game_ID, GAME_DATE, MATCHUP, WL, MIN, FGM, FGA, FG_PCT, FG3M, FG3A, FG3_PCT, FTM, FTA, FT_PCT, OREB, DREB, REB, AST, STL, BLK, TOV, PF, PTS, PLUS_MINUS, VIDEO_AVAILABLE`. That is every counting stat you need for points / rebounds / assists / steals / blocks / threes / turnovers props, plus FG/FT denominators for usage‑based modeling.

Rate limits: undocumented but real (Cloudflare‑enforced). Practical guidance from the wehoop/hoopR community is roughly 1 request every 0.5–1.0s with rotating UA, or use a residential proxy pool for backfills. `wehoop-wnba-stats-data` explicitly uses a proxy list for daily refresh jobs because the stats API will throttle a single residential IP doing >~30 requests/min.

### 3) BallDontLie WNBA API (`api.balldontlie.io/wnba/v1/...`)

Yes, BallDontLie covers WNBA — data goes back to 2008 — but the free plan is restrictive. Per the wnba.balldontlie.io Account Tiers table, the free tier shows "Yes" only for Teams, Players, and Games; Active Players, Injuries, Standings, and Play‑by‑Play move to ALL‑STAR ($9.99/mo), and Player Stats, Team Stats, Player Season Stats, Team Season Stats, Betting Odds, and Player Props are GOAT‑only ($39.99/mo). The per‑game player box‑score endpoint you need for projections is `GET https://api.balldontlie.io/wnba/v1/player_stats`.

Pricing breakdown (WNBA only):

| Tier | Player Stats? | Player Season Stats? | Player Props? | Rate | Price |
|---|---|---|---|---|---|
| Free | No | No | No | 5 req/min | $0 |
| ALL‑STAR | No | No | No | 60 req/min | $9.99/mo |
| GOAT | **Yes** | Yes | Yes | 600 req/min | $39.99/mo |
| ALL‑ACCESS (all sports) | Yes | Yes | Yes | 600 req/min | $299.99/mo |

Auth: pass `Authorization: <API_KEY>` header (no `Bearer` prefix). Pagination is cursor‑based (`?cursor=N`, max `per_page=100`).

Fields returned by `/wnba/v1/player_stats` (per row): `player.{id, first_name, last_name, position, height, weight, jersey_number, college, age}`, `team.{id, conference, city, name, full_name, abbreviation}`, `game.{id, date, season}`, and stats: `min, fgm, fga, fg3m, fg3a, ftm, fta, oreb, dreb, reb, ast, stl, blk, turnover, pf, pts, plus_minus`. There's also a Player Props endpoint (`/wnba/v1/odds/player_props?game_id=…&vendors[]=fanduel`) with prop types: `points, rebounds, assists, threes, double_double, triple_double, points_assists, points_rebounds, rebounds_assists, points_rebounds_assists` — but again, GOAT‑tier.

Practical take: BallDontLie is a great clean data layer if you're going to pay $40/mo anyway; if you're trying to stay $0, **use it only for the free Players endpoint as a name → player_id lookup** and pull actual stats from stats.wnba.com or the SportsDataverse releases.

### 4) Other free, no‑key sources

- **Basketball‑Reference WNBA section** (`https://www.basketball-reference.com/wnba/`): full historical totals, per‑game, advanced, and individual player game logs at `https://www.basketball-reference.com/wnba/players/{letter}/{playerslug}/gamelog/{year}/`. No JSON API — you scrape HTML tables. Sports Reference's robots/ToS allow personal use but restrict commercial redistribution; rate‑limit to ~1 request/3s and cache. Good for cross‑validating stats.wnba.com numbers (they differ occasionally on minutes rounding).
- **WNBA.com / `cdn.wnba.com` live data**: the league publishes live game JSON used by the in‑browser scoreboard at paths analogous to `https://cdn.nba.com/static/json/liveData/...` — these are public, no key, but the schema isn't formally documented.
- **The Odds API** (`https://api.the-odds-api.com/v4/sports/basketball_wnba/...`): the **Starter plan is permanently free at 500 credits/month (no time limit, no trial expiry)** per the‑odds‑api.com's published pricing. Paid plans run from $30/mo (20K credits) to $59/mo (100K), $119/mo (5M), and $249/mo (15M) — the top published tier is $249/mo, not $119. This is the prop‑line source you specifically named. Game odds at `/odds?regions=us&markets=h2h,spreads,totals`; per‑event player props at `/events/{eventId}/odds?markets=player_points,player_rebounds,player_assists,player_threes,player_points_rebounds_assists,…` plus `*_alternate` for X+ milestone markets. Match by `home_team` / `away_team` and `commence_time` to your stats.wnba.com game IDs.

### 5) Python wrappers (no API key)

- **`wehoop-py`** (`pip install wehoop-py`): Python port of the R `wehoop` package. ESPN endpoints for live PBP + box scores. Companion `sportsdataverse-py` exposes `sportsdataverse.wnba.load_wnba_player_boxscore(seasons=range(2002, 2026))`, `load_wnba_team_boxscore`, and `load_wnba_schedule` — these download pre‑built season files from the GitHub Releases (release tags `espn_wnba_player_boxscores`, `espn_wnba_team_boxscores`, `espn_wnba_pbp`, `espn_wnba_schedules` in `sportsdataverse/sportsdataverse-data`). Returns polars by default; pass `return_as_pandas=True` for pandas. **This is the fastest way to assemble a multi‑season training set.**
- **`swar/nba_api`** (`pip install nba_api`): the canonical NBA stats wrapper, also supports WNBA via `LeagueID='10'`. Has `from nba_api.stats.static import players; players.get_wnba_players()`. Most endpoints (`PlayerGameLog`, `LeagueGameLog`, `BoxScoreTraditionalV2`, `LeagueDashPlayerStats`, etc.) accept `league_id_nullable='10'` or `league_id='10'`. Caveat: by default it points at `stats.nba.com`; for full WNBA coverage some users override the host to `stats.wnba.com`. Custom per‑request proxy, header, and timeout support shipped in **v1.1.1** ("Release v1.1.1 — Added Individual Proxy, Header, and Timeout Support", 2019‑04‑07 on github.com/swar/nba_api/releases).
- **`basketballrelativity/py_ball`** (`pip install py_ball`): documents WNBA explicitly (`league_id='10'`). Slightly less maintained than `nba_api` but cleaner WNBA‑specific docs.
- **`rozzac90/wnba`** (GitHub only): a dedicated lightweight `stats.wnba.com` wrapper.
- **R alternative if you also work in R**: `wehoop` is the most complete WNBA package. The development version on GitHub (3.0.0) "ships 80 ESPN basketball endpoint wrappers (39 espn_wbb_* + 41 espn_wnba_*)" per the README, alongside extensive `stats.wnba.com` wrappers; note the current CRAN‑published stable version is 2.1.0 (May 2026), so the 41‑function count applies to the GitHub dev build, not stable CRAN.

Avoid: `Ahimsaka/wnbAPI` — explicitly archived and broken after stats.wnba.com schema changes.

## Recommendations

**Stage 1 — Backfill (one‑time):** Use `sportsdataverse-py`'s `load_wnba_player_boxscore(seasons=range(2018, 2026))` to pull ~7 seasons of player‑game rows in one call. This is free, no API key, no rate‑limit risk (it's downloading static GitHub release files). Validate field coverage matches your prop markets (PTS, REB, AST, STL, BLK, FG3M, TOV, MIN, FGA, FTA — all present).

**Stage 2 — Daily incremental refresh:** Hit `https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard?dates=YYYYMMDD` once per day to get the previous night's `event` IDs, then iterate `https://site.web.api.espn.com/apis/site/v2/sports/basketball/wnba/summary?event={id}` for player box scores. Cache aggressively. **No key required.** As a cross‑check, also pull `https://stats.wnba.com/stats/leaguegamelog?LeagueID=10&Season=2025&SeasonType=Regular+Season&PlayerOrTeam=P&...` with the correct headers — Stats.WNBA is canonical for minutes and gives consistent `Player_ID`s for joining.

**Stage 3 — Player ID / roster mapping:** Use `commonallplayers?LeagueID=10` (stats.wnba.com) as your canonical player roster; cross‑map to ESPN `athlete.id` via fuzzy name + team match (you'll need both because The Odds API uses player **display names**, not IDs).

**Stage 4 — Prop‑line ingestion:** Use The Odds API `/v4/sports/basketball_wnba/events/{eventId}/odds?regions=us&markets=player_points,player_rebounds,player_assists,player_threes,player_steals,player_blocks,player_turnovers,player_points_alternate,player_rebounds_alternate,player_assists_alternate&oddsFormat=american`. Match `outcomes[].description` (player display name) + `outcomes[].point` (the line) to your projection. Their `commence_time` and team names give you the deterministic join to ESPN/Stats.WNBA game IDs. Start on the permanently free Starter plan (500 credits/mo) and only upgrade to $30/mo (20K) once you exceed it.

**Stage 5 — Modeling output:** Project a Normal/Negative‑Binomial distribution for each stat per player‑game using rolling features from Stage 1 + 2 (last‑5, last‑10, season‑to‑date, vs‑opponent, home/away, pace‑adjusted). Compare projected median + variance to the Stage‑4 line to get vig‑free implied edge.

**Thresholds that should change your approach:**
- If you find stats.wnba.com starts returning 403/429 consistently → either rotate UAs and proxies, or fall back to ESPN summary parsing (which has every counting stat you need anyway). Don't pay for BallDontLie just to avoid Cloudflare — ESPN is the better free fallback.
- If you need play‑by‑play or shot‑location data (for usage / role / defender features) → only stats.wnba.com (`playbyplayv2`, `shotchartdetail`) and ESPN's PBP endpoint expose it for free; BallDontLie free tier does not.
- If you exceed ~500 stats.wnba.com requests/hour from a single IP, you'll likely be Cloudflare‑throttled. At that point either move to the `sportsdataverse-data` GitHub release files (no rate limit), or rotate residential proxies as `wehoop-wnba-stats-data` does.
- If you ever need >2 sportsbooks of prop lines or historical prop lines → The Odds API ($30‑$249/mo) or OpticOdds is required; BallDontLie player‑props endpoint is real‑time only, no history.

**Recommended minimal stack (free, $0/mo total data cost, including Odds API Starter):**
1. `sportsdataverse-py` for historical bulk pulls.
2. `requests` + headers preset to call `stats.wnba.com` for live season data and dashboards.
3. `requests` to call `site.api.espn.com` for daily scoreboards + game summaries (no headers needed).
4. The Odds API Starter (500 credits/mo, permanently free) for prop lines.

## Caveats

- **Every "free" WNBA endpoint here is unofficial.** ESPN's site API and stats.wnba.com are both reverse‑engineered; neither has an SLA. Build with timeouts, retries with exponential backoff, and a clean fallback path (if ESPN's path changes, fall over to stats.wnba.com and vice versa).
- **CORS:** ESPN's `site.api.espn.com` is generally browser‑callable; `stats.wnba.com` is **not** — you need a server‑side proxy for client‑side dashboards.
- **`nba_api` WNBA support is real but partial in practice.** `league_id='10'` is documented and `players.get_wnba_players()` works, but several endpoints route by default to `stats.nba.com`; for some WNBA‑specific endpoints you may need to override the host to `stats.wnba.com`. The R `wehoop` package and `rozzac90/wnba` are more battle‑tested specifically against the WNBA host.
- **BallDontLie's "free WNBA" is marketing‑speak.** The free tier is essentially a roster/schedule API; the actual player_stats / season averages / props / play‑by‑play all require paid tiers. Plan for $39.99/mo if you commit to it, or stick with ESPN + stats.wnba.com.
- **Data starts at different seasons by source:** SportsDataverse releases (ESPN data) cover 2002+; BallDontLie covers 2008+; stats.wnba.com covers 1997+ for some endpoints but advanced stats are inconsistent before ~2014.
- **Field name differences across sources can silently break joins** — e.g., turnovers are `TOV` on stats.wnba.com, `turnover` on BallDontLie, `turnovers` in the ESPN player stat array. Normalize on ingest.
- **Player‑ID systems are not unified.** stats.wnba.com uses its own IDs (e.g., Sabrina Ionescu‑style 7‑digit IDs), ESPN uses its `athlete.id` (e.g., `4066533`), BallDontLie has its own integer IDs, and Basketball‑Reference uses slugs. Build a cross‑walk table early; do not try to join on names alone.
- **Sportsbook prop‑line names sometimes mismatch official rosters** (initials, accents, hyphens). Use fuzzy matching with manual overrides for known edge cases.
- **The 2026 WNBA season data on SportsDataverse releases may lag by a few hours** versus live ESPN/stats.wnba.com — confirmed by a 404 on `play_by_play_2026.rds` in our verification. For live projections, do not rely on the GitHub release files alone; pair them with same‑day API calls.