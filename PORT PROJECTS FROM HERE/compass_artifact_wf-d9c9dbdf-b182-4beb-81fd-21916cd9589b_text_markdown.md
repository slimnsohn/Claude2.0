# Profitable WNBA Player Prop Models and Orthogonal LLM Integration: A Research Report

## TL;DR

- **Build a distributional, Bayesian-shrunk projection per player–stat–game, not a point estimate**: a Negative Binomial (for points/rebounds) or Poisson–Gamma model with hierarchical priors by position handles WNBA's 40-game small-sample problem and produces calibrated over/under probabilities that beat naive point-estimate-plus-Normal approaches; combine it with a market-consensus blend (Unabated/OpticOdds-style devigged line) and stake at quarter-Kelly to survive WNBA's tight prop limits.
- **The free-data stack that actually works in WNBA is `wehoop` (R) + `sportsdataverse-py` (Python) + `pbpstats` for possessions + The Odds API for `player_points`, `player_rebounds`, `player_assists` and their `_alternate` markets**; every other vendor is either paid (Unabated, OpticOdds, SportsDataIO) or stale (`py_ball`, `wnbAPI`).
- **The highest-leverage, non-obvious uses of LLMs are NOT prediction — they're (a) parsing beat-writer tweets/coach quotes into structured rotation/usage deltas before the market reacts, (b) a multi-agent "stats vs. injury vs. market" debate that flags model–context disagreements, and (c) generating an auditable bet thesis you can grep through during a losing streak**; using an LLM as the primary probability source is documented to be miscalibrated and overconfident (FermiEval found "nominal 99% intervals cover the true answer only 65% of the time on average").

---

## Key Findings

### Model design — what actually moves the needle
1. **Pace normalization is mandatory in WNBA, more than in NBA.** WNBA team-pace variance is larger because the league has been globally accelerating: from 2017's three teams above 80 possessions/40 to nine teams above 80 in 2020 (FiveThirtyEight). Stats must be expressed per-100-possessions, then re-multiplied by the projected pace of the specific matchup (team pace × opponent pace effects, averaged), not season averages. `stats.wnba.com` exposes `PACE` and `PACE/40` for free.
2. **Distribution > point estimate.** Books increasingly price props with parametric distributions (OpticOdds). A point-projection-vs-line approach loses to a Negative Binomial that learns a per-player dispersion parameter and naturally puts mass on "sensational" outcomes (Binomial Basketball, 2023).
3. **Bayesian shrinkage by position is the right answer to WNBA's 40-game season.** Hierarchical models (Williams, Schliep, Fosdick & Elmore, *Annals of Applied Statistics* 19(4):3492–3507, December 2025, DOI: 10.1214/25-AOAS2079) cluster players and teams by shooting tendency with population priors; this dominates plain MLE for low-sample players and mid-season call-ups.
4. **XGBoost/LightGBM beats ridge only when feature interactions matter and you have enough data.** A University of Washington 2023 project achieved RMSE 3.13 on NBA game-score vs. 7.33 naive — but that's 1230 games/season × 15 years. For WNBA's ~40-game season × 12–14 teams, ridge regression with hand-engineered interaction features is competitive and far more stable; gradient boosting only pays off when you stack 5+ seasons.
5. **Back-to-back matters less than people assume in the WNBA — but rest still moves ~3 points and 0.5% FG.** A Medium analysis of stats.wnba.com box scores 1997–2023 (Mayzie Hunter) found B2B teams win 46%, 1-day rest 50%, 2+ days 51%; an extra day of rest is worth ~3 points and ~0.5% better FG%. *This is the closest WNBA-specific number available — there is no peer-reviewed WNBA analogue to Lewis et al.'s 2018 NBA paper on B2B injury risk.* Note also a structural break: WNBA teams flew commercial pre-2024; per Commissioner Cathy Engelbert's May 7, 2024 announcement to sports editors, "We intend to fund a full-time charter for this season" (Delta Airlines as primary operator), projected at "around $25 million per year for the next two seasons." Travel-fatigue effects estimated on historical data therefore likely do not fully generalize to 2024+.
6. **Same-game prop correlation is real and exploitable, but obvious correlations are priced in.** Star-PTS × team-spread correlations run 0.35–0.45 in NBA; second-order correlations (e.g., backup PG's assists when starter is out) stay soft (Sportsboom, Wizard of Odds).
7. **The closing line is the benchmark.** Beating the closing line consistently is the only robust indicator of long-term skill in props (FadeReport).

### LLM integration — what's actually useful
1. **LLMs are bad at being the predictor and good at being the connective tissue.** The arXiv FermiEval study (2510.26995) shows modern LLMs' "99%" confidence intervals contain truth only ~65% of the time — they are systematically overconfident. Use them to extract, structure, narrate, and arbitrate; not to output the headline probability.
2. **Multi-agent debate beats single-shot LLM judgments in finance-analogue tasks.** TradingAgents (arXiv 2412.20138, open-sourced at github.com/TauricResearch/TradingAgents) and FinDebate (arXiv 2509.17395) both show measurable Sharpe/calibration improvements from structured agent debate with a Popperian/safe-debate protocol. A direct port: "stats analyst" agent + "news/injury analyst" agent + "market analyst" agent + "risk manager" judge, deciding whether a flagged bet survives.
3. **RAG with structured metadata beats vanilla embeddings.** SRAG (arXiv 2603.26670) reports, using GPT-5 as an LLM-as-judge, a 30% improvement in scores on answers in a question-answering system (p-value = 2e-13), with the strongest gains on "comparative, analytical and predictive questions" — exactly the questions you ask of historical matchup notes.

---

## Details

### Part 1 — Advanced Model Design for WNBA Player Props

#### 1.1 Feature Engineering

**Pace adjustment.** WNBA games are 40 minutes (not 48), so pace is reported as possessions/40. The canonical formula (Captain Calculator, derived from Dean Oliver): `Pace = Minutes × (Team Poss + Opp Poss) ÷ (2 × Team Min ÷ 5)`. Raw counting stats are misleading because the spread is wide: in 2020 the Aces averaged 94.0 PPG vs. the previous record's 93.9 (2010 Mercury), largely driven by pace. Free pace data: `stats.wnba.com/teams/advanced/`, FOX Sports, RotoWire, and via `wehoop::wnba_teamestimatedmetrics()`. Implementation: for each player-stat, compute *rate per 100 possessions or per minute*, then re-multiply by projected matchup pace, where projected pace is best estimated as a blend (e.g., 0.5 × team pace + 0.5 × opponent pace, with a small home-court adjustment).

**Usage rate and lineup context.** USG% formula (Dean Oliver): `100 × (FGA + 0.44 × FTA + TOV) × (Team Min ÷ 5) / (Min × (Team FGA + 0.44 × Team FTA + Team TOV))`. The critical move is **on/off splits**: when a high-usage teammate is out, the absorbed possessions are not uniform — they concentrate on the next-highest USG% players already on the court. Quantify via WOWY (With-Or-Without-You) analysis. `pbpstats` exposes lineup-on-court data needed for per-lineup usage. Practical pattern: build a player-by-teammate usage delta matrix from 2–3 seasons of PBP; when a starter is ruled out, look up the delta column to project the new USG% for every other rotation player, then rescale their PTS/AST/REB projections proportional to expected USG%.

**Opponent defensive ratings.** From free data:
- Team DEF_RTG at `stats.wnba.com/teams/advanced/`.
- Position-vs-position points-allowed at `rotowire.com/wnba/opp-avg.php` (filterable by G/F/C) and `linestarapp.com` (defense-vs-position matchup ratings).
- A *defender-specific* difficulty rating requires matchup data (who guarded whom). The free path: parse PBP for closest-defender shot attempts (limited in WNBA tracking), or back into it via on-court splits — when defender X is on the floor, how does opponent player Y's efficiency change vs. baseline? This is noisy but the best free option.

**Back-to-back and travel fatigue.** The empirically grounded WNBA-specific deltas (Hunter 2024 blog analysis of stats.wnba.com 1997–2023): teams on zero rest win 46%, teams with 1 day of rest win 50%, teams with 2+ days win 51%; an extra rest day is worth ~3 PPG and ~0.5% FG%. **Caveats**: (a) not peer-reviewed, (b) team-level not player-level, (c) the structural break in May 2024 when the WNBA moved from commercial flights to charters (Delta Airlines, ~$25M/year for 2024–25 per Engelbert) likely reduced the rest effect post-2024 and should be modeled as a regime change. The NBA analog (Lewis et al. 2018, PMC6107769): "Simply not playing in back-to-back games can reduce the probability of an injury by almost 16% for the average player." There is no peer-reviewed WNBA replication of this figure.

**Home/away splits.** The MDPI 2024 systematic review (Navarro-Barragán & Jiménez-Sáiz) found home-court advantage in basketball is driven by player performance, position, and sleep, and that HA effects compressed dramatically in COVID empty-arena games (56% of reviewed articles were 2021–2024 precisely because of this natural experiment). For WNBA specifically the directional finding from the same review is that HA exists but the *between-team variance* is large (the Lynx were 19-2 at home in 2025, Target Center +112.1 ORtg; the Valkyries were voted #1 in home-court advantage in the 2026 GM survey). Model HA as a **team-specific** intercept, not a league constant.

**Recency weighting.** For a 40-game season, fixed rolling windows (e.g., last 10 games) lose information and have unstable cutoffs. **Exponentially weighted moving averages (EWMA) with a half-life of ~5–8 games** is the better choice (Hardball Times: "day-to-day weighting usually relies on fitting an exponential decay factor"). The decay parameter should be tuned per stat: minutes/usage move slowly (long half-life), 3PT% and FG% are noisy (longer half-life), assists/turnovers per minute are stable (medium). Use empirical Bayes to set the prior weight: a player with 5 games gets 60–70% prior, 30–40% data; a player with 25 games gets the inverse.

**Matchup-specific features.** Build a (defender_team, offensive_position) matrix of allowed efficiency (PPP, eFG%, REB%) per minute, then for each game compute the expected allowed efficiency given projected position matchups. A common WNBA pitfall: positionless basketball means "matchup" is often a 1-of-3-defenders weighted average; use lineup data from `pbpstats` to estimate the most-likely primary defender by minute share.

**Minutes volatility.** Coach rotation patterns are *the* dominant source of prop variance in WNBA — a player on a 28 ± 6 minute distribution has very different prop EV than a 28 ± 2 player even with the same mean. Model minutes as its own distribution (Normal or Gamma) with features for: foul-rate-per-minute (WNBA disqualification is 6 personal fouls, per the 2024 WNBA Rule Book), expected game competitiveness (blowout → starters sit, garbage time gives bench scoring), and recent minute trend. Then convolve minutes-distribution × per-minute-stat-distribution to get the final stat distribution, rather than multiplying point estimates.

#### 1.2 Model Architecture

**Regression vs. ML.** For WNBA's roughly 4–5,000 player-game observations per season, **ridge regression with carefully engineered interaction terms is competitive with XGBoost/LightGBM and far more stable**. Use XGBoost when you have ≥3 seasons of pooled data and want non-linear interactions (e.g., pace × rest × usage). The Washington 2023 NBA project showed XGBoost achieves RMSE 3.13 vs. 7.33 naive on game score with 5+ seasons of NBA-scale data; expect smaller absolute gains on WNBA.

**Bayesian approaches.** Williams, Schliep, Fosdick & Elmore (2025, *Annals of Applied Statistics* 19(4):3492–3507) demonstrate a hierarchical Bayesian framework that clusters players and teams by shooting tendency — directly applicable to WNBA props because it produces a full posterior predictive distribution per player. Implementation: PyMC or Stan. Hyperparameter: position-level priors anchored to league-wide distributions, with player-level intercepts shrunk toward position means. This is the single most important architectural choice for handling mid-season trades and new-player call-ups in WNBA.

**Distribution modeling.** Counts (points, rebounds, assists, 3PM) are over-dispersed relative to Poisson. The **Negative Binomial with a learned per-player dispersion parameter** is preferred (Binomial Basketball: "an extra parameter for each player that indicates how consistent that player is"; Squared2020 NB regression for 3PT). Variance = X + α²X² grows quadratically with mean, matching empirical basketball counts. For continuous-ish stats like points (which are 2-/3-pointer mixtures), a hurdle Negative Binomial or compound Poisson can outperform pure NB. Monte Carlo simulation (OpticOdds: "Probability Paths: Monte Carlo vs. Parametric") is the right choice when you need correlated multi-stat outputs (PRA, PTS+AST, etc.) — sample joint minute/usage/eFG% draws and compute all stats from one sampled game.

**Ensemble with market consensus.** Use the de-vigged consensus from sharp books (Pinnacle, Circa, Bookmaker — exposed via the Unabated Line or constructible from The Odds API by averaging market makers and removing the vig) as a *prior* the projection model is blended with. Practical blending: posterior probability = w × model_p + (1−w) × market_implied_p, with w tuned by historical Brier score on holdout. Most retail bettors should run w in [0.2, 0.5] — your model is rarely better than a sharp consensus, and a blend has lower variance.

**Transfer learning from NBA.** Useful for: (a) shared players (Achilles tendon rupture cohort study, PMC11452890, found 102 professional NBA+WNBA players in a 30-year window with overlap analyzable across leagues), (b) age-curve priors, (c) shot-quality decay. Caution: the leagues differ in pace, three-point line distance (WNBA: 22'1.75" center, NBA: 23'9"), 40-minute vs 48-minute games, and substitution patterns. Best practice is to use NBA data only as a *prior* for shared structural parameters (e.g., the relationship between USG% and TS%) and let WNBA data dominate the level estimates.

**Kelly Criterion and bet sizing.** Full Kelly: `f = (b·p − q)/b`. WNBA prop limits are tight ($50–$500 typical), so the constraint is usually exposure-per-line, not per-bankroll. Use **quarter-Kelly (0.25 × full Kelly)** as the recommended starting point (Betstamp, Optimal Bet: "Half Kelly sacrifices only 25% of the growth rate but cuts volatility dramatically"). Adjust downward further when (a) model is new/uncalibrated, (b) bet is on alt lines with thin liquidity, (c) correlated exposure on the same game already exists. With a 55% true win rate at +110 odds and a $10,000 bankroll, full Kelly is 14.1%; quarter Kelly is ~3.5% — about right given prop liquidity.

#### 1.3 Market Exploitation

**Line shopping.** Programmatic: pull The Odds API endpoint `/v4/sports/basketball_wnba/events/{eventId}/odds?markets=player_points,player_rebounds,player_assists,player_threes,player_points_alternate,...&regions=us`. The Odds API covers WNBA player props for most US bookmakers; alternate lines via `_alternate` suffix. Cross-reference against Unabated, OpticOdds (which integrated The Crowd's Line AI WNBA model — announced April 20, 2026, live by May 12, 2026; per OpticOdds VP Ryan Weinstock: "Working with The Crowd's Line AI to offer model-based WNBA pricing through our API reinforces OpticOdds's focus on bringing advanced market-grade intelligence to sports betting"), or your own consensus. The half-point gain at -110 is worth ~2% of EV — *always* shop the number.

**Sharp money signals.** Three documented signals from the line-movement literature (FadeReport, BettorEdge, SportsFirst):
- **Reverse line movement (RLM)**: line moves opposite the majority of tickets.
- **Steam moves**: coordinated 0.5–1+ point moves across 5+ books within 5–15 minutes.
- **Bet% vs. money% divergence**: when ≥10% gap (e.g., 30% of tickets but 60% of money on one side).
In WNBA player props, RLM on a player line within 90 minutes of tip-off is a much stronger signal than in NBA because WNBA prop markets are thinner — when a sharp book moves a WNBA prop, it's almost always informed.

**Alternate lines.** `player_points_alternate` exposes the full ladder (e.g., 15+, 20+, 25+ for a player). The EV opportunities are different from main lines: (a) bookmaker pricing is often a single distribution fit, so if your model's distribution shape differs, you may find edge at the *tails* even when the main line is fair; (b) alternate-line markets are less efficient because they get less volume — sharps often only attack the main number.

**Correlation between props.** Within-game correlations exposed in correlated SGP markets: PTS↔AST 0.30–0.40 for primary playmakers, PRA combos with team total ~0.50, PTS↔threes-made 0.5–0.6 for high-volume shooters (Sportsbook Odds Calculator data). Books that don't fully model correlation (smaller regional books or some props-only books) systematically misprice multi-leg SGPs in the *positively correlated* direction. The exploit is the inverse of what most retail bettors do: instead of stacking obvious positive correlations (which books price tightly), find **second-order positive correlations** like "backup PG over assists when starter is out" + "team total under" when the starter's absence is also expected to slow the game.

### Part 2 — LLM Integration

#### 2.1 Unstructured Data Ingestion — the highest-EV LLM use

The clearest, most underexploited use of LLMs in a betting pipeline: **structured signal extraction from unstructured pre-game text**. Beat-writer tweets, coach press conferences, team-released injury reports, and DraftKings/PrizePicks line movement narratives all contain information *before* the line fully reflects it.

Practical pattern:
- Stream tweets from a curated list of WNBA beat writers (Howard Megdal, Khristina Williams, team beats) via the X API.
- Pipe each tweet through a small/fast model (Claude Haiku 4.5, GPT-4o-mini) with a structured-output prompt: `{"player": str, "team": str, "status": one of [questionable, probable, doubtful, out, healthy, role_change], "minutes_delta": optional float, "confidence": 0..1, "rationale": str}`.
- Route any classification with `status != null` to a model re-projection trigger.
- Persist all outputs into a Postgres or DuckDB table so backtests have the same news context.

Pitfalls: (a) hallucinated minutes deltas — constrain the model to "minutes_delta ∈ [-40,40] or null" and reject anything not directly quoted; (b) trusting one report — require ≥2 independent sources before triggering a re-projection in production.

#### 2.2 Contextual Reasoning Override

When the statistical model flags an over/under but recent context (a player just came back from injury, a coach quoted a minutes restriction, a player just had a child) suggests the model is stale, an LLM can serve as the *override* gate. Implementation: pass the model's projection, the recent statistical trend, and a curated context blob to Claude/GPT with a prompt like "Given the statistical projection of 17.8 points and the following context, should the projection be (a) accepted, (b) reduced by 10–20%, or (c) the bet skipped? Return JSON with rationale." Treat this as a *filter on bets*, not a probability source.

#### 2.3 Automated Bet Thesis Generation

For every flagged bet, produce a 2–4 sentence human-readable rationale stored alongside the bet record. Example prompt format:
```
You are writing a one-paragraph bet thesis. Inputs:
- Player: {player}, Stat: {stat}, Line: {line}, Side: {side}, Model edge: {edge}%
- Projection: mean={mu}, dispersion={alpha}
- Top 3 features by SHAP: {feature_list}
- Recent news: {news_blob}
- Line movement: {opener} → {current}
Output 3 sentences explaining (1) statistical case, (2) contextual case, (3) market case.
```
Value: post-hoc review of losing weeks is dramatically easier when each bet has a frozen thesis.

#### 2.4 Anomaly Explanation

When the model flags an outlier (e.g., a player line implied at 12.5 pts but model says 18.0), an LLM can run a tree of plausible explanations: "Is the line stale relative to a known injury? Is the opponent's defensive rating an outlier? Is the player on a known role change?" — and rank them by likelihood. This is essentially a structured-thought scaffold; combine with retrieval over your news/injury database.

#### 2.5 News/Injury Classifier

A fine-tuned (or few-shot) classifier on a small WNBA injury corpus is straightforward. Categories: `confirmed_out`, `game_time_decision`, `back_from_injury`, `minutes_restriction`, `personal_absence`, `precautionary_rest`. Plug into the projection trigger from 2.1.

#### 2.6 LLM as Ensemble Voter — use with caution

The arXiv FermiEval study (2510.26995, October 2025) is unambiguous: "nominal 99% intervals cover the true answer only 65% of the time on average" across modern LLMs, and they exhibit "perception-tunnel" overconfidence under uncertainty. **Do not** use a raw LLM probability as a direct input to Kelly sizing. If you want LLM-as-voter, apply post-hoc calibration: (a) collect ~500 historical bet outputs from the LLM with ground truth, (b) fit isotonic regression or temperature scaling on confidence vs. outcome, (c) use the calibrated probability as a *small-weight* (5–15%) blend with the statistical model.

#### 2.7 Prompt Engineering for Structured Prediction

Three concrete prompt-engineering moves that improve reliability:
- **Force JSON schema output**, not free text. Use Anthropic's tool use / OpenAI's response_format with a strict schema including `probability_over: number ∈ [0,1]`, `confidence: number ∈ [0,1]`, `key_factors: array of strings`.
- **Provide the prior** (the market-implied probability) and instruct the model to *adjust* from it, not produce de novo. This dramatically reduces overconfidence.
- **Multi-sample + median** (self-consistency): sample 5 outputs at temperature 0.5, take the median probability. Reduces variance from single-shot stochasticity.

#### 2.8 Confidence Calibration

Methods documented in the literature (Latitude blog summary, arXiv 2505.21772, arXiv 2510.26995):
- **Temperature scaling**: fit a single T parameter on a validation set by minimizing NLL. BERT-style work shows optimal T usually 1.5–3.
- **Isotonic regression**: fit a monotonic mapping from raw confidence to empirical accuracy. More flexible than temperature scaling but needs more data.
- **Conformal prediction**: produces empirically-valid confidence intervals; FermiEval showed conformal correction recovers nominal 99% coverage and reduces the Winkler interval score by 54%.
- **APRICOT-style automated calibration** (Latitude): system uses input/output patterns to adjust confidence post-hoc.
Track Expected Calibration Error (ECE) and Brier score weekly; recalibrate monthly.

#### 2.9 Retrieval-Augmented Generation (RAG) for Betting Context

Build a vector store of: historical matchup notes, coach rotation tendencies (e.g., "Cheryl Reeve has shortened the rotation in the last 5 minutes of games in 80% of close games this season"), beat-writer archives, your own prior bet theses, defensive scheme notes. SRAG (arXiv 2603.26670) shows, judged by GPT-5 as LLM-as-judge, a 30% improvement (p = 2e-13) in QA answer scores by tagging chunks with topics/sentiment/types — for betting this means tagging chunks with `{team, player, season, topic ∈ [rotation, scheme, injury, role], game_outcome}`. Tools: ChromaDB or pgvector for the store; sentence-transformers or OpenAI `text-embedding-3-small` for embeddings; LangChain or LlamaIndex for orchestration; Anthropic's contextual retrieval pattern for the retrieval prompt.

#### 2.10 LLM for Line Interpretation

A novel pattern: feed the LLM a line and ask it to *reverse-engineer the book's model*. Prompt: "DraftKings has set A'ja Wilson's points at 22.5 (-115/-105). Given her season average of 24.1, recent 5-game average of 26.0, and tonight's matchup, what assumptions must the book be making to justify this line?" The output isn't a probability — it's a list of testable assumptions you can check (e.g., "the book may be assuming minutes restriction"). This is the LLM doing *theory generation*, not prediction.

#### 2.11 Automated Backtest Narration

After each weekly/monthly backtest, dump the bet log and PnL by segment (player, stat type, line range, model confidence bucket, day-of-week) to the LLM with a prompt: "Write an honest assessment of where this model won and lost, with specific bets and rationale. Flag any segment with >20 bets and ROI < -5% as a candidate for exclusion." This is meaningfully better than dashboards because it forces narrative integration: humans miss patterns spread across multiple dimensions; LLMs catch them.

#### 2.12 Multi-Agent Architecture

The strongest research signal here comes from finance. TradingAgents (arXiv 2412.20138, open-sourced at github.com/TauricResearch/TradingAgents) and FinDebate (arXiv 2509.17395) demonstrate measurable performance gains from structured multi-agent debate, with the latter showing "calibrated confidence levels" via a "safe debate protocol that enables agents to challenge and refine initial conclusions while preserving coherent recommendations."

Direct port for WNBA props:
- **Stats Analyst** — has tools to query the projection model, returns mean/distribution/SHAP.
- **Injury/News Analyst** — has RAG access to news store, returns context narrative.
- **Market Analyst** — has The Odds API access, returns line history and CLV-projection.
- **Risk Manager (judge)** — sees all three reports, applies position limits, correlated-exposure constraints, and Kelly cap; outputs final stake.
Use ReAct-style prompting (Yao et al. 2023, already standard in TradingAgents). Critical guardrails from the literature: bound the debate ("pre-debate stance is fixed, roles are prohibited from changing direction"; FinDebate); require every claim to be anchored to a verifiable reference; cap rounds at 2–3 to control cost. The Popperian Multi-Agent Debate framework (arXiv 2510.17108) — bull vs. bear under Karl Popper protocol — reported "baseline ≈ 1,900 s/case; SAS ≈ 11.6 s; PMADS ≈ 92.0 s" on a credit-reasoning task, i.e., the multi-agent system was ~7.9× slower than a single-agent system (SAS) but ~21× faster than human experts, with materially better reasoning depth.

**Pitfalls.** Latency and cost compound (a 4-agent debate on 60 bets = 240 LLM calls). Solve with caching, parallel agent calls (independent agents query simultaneously), and using smaller models (Haiku, GPT-4o-mini) for the analysts and a larger model (Claude Sonnet 4.5, GPT-4o) only for the judge.

### Implementation reference — the free WNBA data stack

- **`wehoop` (R, sportsdataverse)** — github.com/sportsdataverse/wehoop. Most comprehensive free WNBA package. Per the CRAN description: "A scraping and aggregating interface for the WNBA Stats API <https://stats.wnba.com/> and ESPN's <https://www.espn.com> women's college basketball and WNBA statistics. It provides users with the capability to access the game play-by-plays, box scores, standings and results." `load_wnba_pbp()` returns ~1.78M rows of PBP from 4,674 games. Actively maintained (v3.0.0 in 2026 ships 80 ESPN basketball endpoint wrappers).
- **`sportsdataverse-py` (Python)** — github.com/sportsdataverse/sportsdataverse-py; `sportsdataverse.wnba` module covers schedule, calendar, game rosters, player and team boxscores. Python 3.9–3.14, Polars backend with `return_as_pandas=True` option.
- **`pbpstats`** — github.com/dblackrun/pbpstats. Possession-level enrichment of NBA/WNBA PBP with lineup-on-floor for every event, possession start/end, shot-zone breakdowns. Indispensable for usage/on-off splits.
- **`nba_api`** — github.com/swar/nba_api (v1.11.4). Has `players.get_wnba_players()` and team finders for WNBA but most analytical endpoints are NBA-centric; useful for player ID lookups.
- **`py_ball`** — github.com/basketballrelativity/py_ball. Self-described as "Python API wrapper for stats.nba.com with a focus on NBA and WNBA applications." Use `league_id='10'` for WNBA. Less actively maintained.
- **`nba_scraper`** — adds `wnba_scrape_game` from v1.0.8 (back to 2005).
- **`wehoop-wnba-data`** — github.com/sportsdataverse/wehoop-wnba-data. Pre-built RDS releases per season (`play_by_play_2026.rds`, etc.).
- **`stats.wnba.com` raw endpoints** — direct access; same endpoints wrapped by `wehoop`/`py_ball`.
- **AVOID `wnbAPI`** (github.com/Ahimsaka/wnbAPI) — abandoned, broken after WNBA API revision.
- **The Odds API** — `/v4/sports/basketball_wnba/...`. Free tier available; historical odds for featured markets back to May 2022, player props back to May 2023.

---

## Recommendations

**Stage 1 (week 1–2, build the bones).** Use `wehoop` (R) or `sportsdataverse-py` (Python) to load 5+ years of WNBA PBP and box scores; use `pbpstats` for lineup-aware possession data. Pull live odds from The Odds API (`player_points`, `player_rebounds`, `player_assists`, `player_threes`, plus their `_alternate` variants). Build a ridge regression projection per stat with features: pace-adjusted per-minute rates (EWMA half-life ~6 games), opponent DEF_RTG, position-vs-position allowed, B2B/rest, home/away, projected minutes (separate model). Stake at quarter-Kelly on a market-blend probability (0.3 model + 0.7 sharp consensus initial weighting).
- **Benchmark to advance**: 4+ weeks of paper-trading with CLV (closing line value) positive in aggregate.

**Stage 2 (week 3–6, get distributional).** Replace the point-projection-vs-Normal approach with per-player Negative Binomial fits (statsmodels `NegativeBinomial`) for counts; add minutes as its own Gamma distribution; convolve via Monte Carlo (10,000 sims per player-game). Add hierarchical Bayesian priors by position (PyMC). Add same-game correlation matrices for SGP plays.
- **Benchmark to advance**: ROI > +2% (after vig) on ≥300 bets, Brier score < 0.235, ECE < 0.04.

**Stage 3 (week 6–10, add LLM connective tissue).** Implement: (a) tweet/news classifier (2.1) into a structured signals table; (b) bet-thesis generator (2.3) writing every bet's rationale; (c) backtest narrator (2.11) running weekly. Do NOT yet put an LLM in the probability path.
- **Benchmark to advance**: thesis generator producing readable output 95%+ of the time; ≥3 cases where the news classifier triggered a re-projection that the line then moved toward.

**Stage 4 (week 10+, multi-agent debate).** Stand up the four-agent architecture (2.12) gated as a *filter*, not a probability source. The risk manager can shrink stake from quarter-Kelly to eighth-Kelly when agents disagree. Add RAG over historical matchup notes (2.9). Calibrate LLM outputs (2.8) with isotonic regression on accumulated bet history before allowing any LLM probability blend.
- **Threshold to back off**: if multi-agent system increases latency past the close of pre-game markets without improving Brier/ROI, drop the judge to a single-shot LLM with structured output.

**Universal benchmarks for when to change strategy.**
- CLV < 0 over 4-week rolling: model has degraded; retrain or reduce stake.
- ECE > 0.06: probabilities are miscalibrated; refit calibration layer.
- Any single segment (player, stat, line range) with >50 bets and ROI < -8%: exclude segment from production.

---

## Caveats

1. **WNBA-specific quantitative evidence is thin.** The cleanest B2B/rest numbers (Hunter 2024 on Medium) are not peer-reviewed; the structural shift to charter flights in May 2024 (Engelbert: "We intend to fund a full-time charter for this season," ~$25M/year for 2024–25) creates a regime change that may invalidate pre-2024 fatigue estimates. There is no peer-reviewed WNBA equivalent to NBA fatigue/injury papers — treat WNBA-specific effect sizes as priors with wide uncertainty.
2. **The 2026 WNBA season has expansion teams** (Golden State Valkyries entered in 2025, Portland and Toronto in 2026), which means defensive ratings and opponent priors are unstable for the first 10–15 games of each expansion year. Increase the prior weight on roster-based features during these windows.
3. **LLM probability outputs are documented to be systematically overconfident** (FermiEval 2025: 65% empirical coverage at 99% nominal). Never plug raw LLM probabilities into Kelly without explicit calibration.
4. **Many commercial sources cited (OpticOdds, SportBot AI, EdgeLock, Unabated)** are vendor blogs with marketing incentives. Where they make specific claims (e.g., SportsFirst's "85%+ accuracy" sharp-money API), treat with skepticism unless independently verifiable.
5. **The Crowd's Line AI / OpticOdds WNBA pricing integration was announced April 20, 2026 and live by May 12, 2026** — this means the public market for WNBA props is now actively being shaped by an institutional ML model. Edges that existed in 2023–2024 against retail-priced WNBA props are compressing rapidly; expect ROI to require more sophistication going forward.
6. **The same-game-parlay correlation numbers cited (0.30–0.60) are NBA/NFL-derived** (Sportsbook Odds Calculator, XSportsbook). WNBA-specific correlations are not published; you must compute your own from historical data before relying on them for SGP betting.
7. **Sports betting carries legal, financial, and addiction risk.** Nothing in this report is investment advice; size positions conservatively and follow your jurisdiction's regulations.