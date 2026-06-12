# Living Population: Scale-Up + Per-Persona Belief Layer

**Date:** 2026-06-11
**Project:** `apps/synthetic-population`
**Status:** Approved design, pending implementation plan

## Goal

Two upgrades to the Synthetic Population Engine:

1. **Scale the population from 1,000 to 5,000 personas**, well-balanced against national
   demographic targets, to tighten confidence intervals and fix known composition gaps
   (strong_rep underweight: 12.6% actual vs ~18% national).
2. **Replace the flat party-level world-update shifts with a persistent per-persona belief
   layer**, so each persona consumes recent news through its own media diet, adjusts its
   opinions individually, retains those adjustments over time (with decay), and stays
   anchored to reality via an automatic calibration gate.

## Constraints

- Real data only. Personas are sampled from real CES 2024 respondents; belief shifts derive
  from real fetched headlines. Never fabricate data to fill gaps (user rule).
- Benchmarks are diagnostic anchors, not tuning targets. The calibration gate dampens
  runaway drift; it does not tune opinions toward poll numbers.
- API keys come from Windows environment variables. Never hardcoded.
- The existing KNN opinion engine (real CES microdata, K=50 neighbors) remains the
  source of baseline opinions. Beliefs are bounded adjustments on top of it.

## Current State (for context)

- 1,000 personas in `data/profiles/registry.json` (40 attributes, 120 archetypes), sampled
  from 60K CES 2024 respondents with census-target weighting.
- `engine/opinion.py` answers questions by KNN-matching a persona to 50 real CES
  respondents and sampling from their actual answers. Calibration ~2.4% MAE on Trump
  approval.
- `api/world_updates.py` fetches RSS headlines, keyword-detects topic/sentiment, and
  computes a flat per-party probability shift applied identically to every member of a
  party. No media-diet filtering, no persistence, no decay. `drift_log` exists on every
  persona but is empty.
- Three one-off population scripts exist (`build_balanced_population.py`,
  `expand_population.py`, `rebalance_population.py`) with hardcoded `TARGET_N = 1000`.

## Section 1 — Population Scale-Up to 5,000

**New script:** `build_population.py --target-n 5000` (consolidates and parameterizes the
three one-off scripts; they are removed after consolidation).

**Method:**
- Fresh sample of 5,000 from the 60K CES pool, without replacement.
- Joint-cell deficit weighting (existing logic from `expand_population.py`): target cell
  counts = product of marginal targets × target_n; sample CES respondents weighted by
  cell deficit.
- Marginal targets: census values for sex, race, education, age_bracket; CES-native
  distributions for party_id and urban_rural. This directly corrects the strong_rep
  underweight.
- Each persona stores its source CES `caseid` as `ces_row_id` for provenance, and
  `batch_id: "ces-balanced-v2-5k"`.
- Profile pipeline unchanged: harmonized demographics, income sampled within CES bracket,
  party-stratified news source assignment, plausibility fix, template backstory.

**Safety and verification:**
- Back up the existing registry to `data/profiles/registry.backup.<timestamp>.json`
  before overwrite.
- Existing snapshots remain readable (they are frozen copies with their own profile data).
- Archetypes rebuilt with `ArchetypeBuilder(min_cell_size=3)`; expect roughly 300–600
  archetypes. Poll auto-complete is pure KNN (no LLM per persona), so runtime impact is
  negligible.
- Builder prints and saves a distribution-vs-target report
  (`data/profiles/build_report.json`); every tracked marginal must be within ±3% of
  target or the builder exits nonzero without writing the registry.

## Section 2 — LLM-Scored News Ingestion

**New module:** `engine/news_scoring.py`.

- RSS fetching in `api/world_updates.py` is unchanged (AP, NPR, BBC, Reuters, Google News).
- One batched LLM call per fetch cycle (Claude Haiku, key from `ANTHROPIC_API_KEY` env
  var) scores all sampled headlines at once. Per headline, the model returns:
  - `topics`: subset of a fixed taxonomy aligned to CES coverage (economy, trump_approval,
    immigration, healthcare, climate, fiscal, education, crime, foreign_policy, social).
  - `direction`: −1.0 to +1.0 (signed strength; sign convention defined per topic in the
    taxonomy, e.g. economy: + = good economic news).
  - `salience`: 0.0–1.0 (how big the story is; drives ambient exposure).
  - `framing`: per outlet family `{right, left, mainstream}` — a multiplier (−1.0 to +1.0)
    for how that family's coverage would spin the story for its audience.
- Strict JSON schema; a malformed response falls back to the keyword scorer for that batch.
- The existing keyword scorer remains as automatic fallback when the API key is missing
  or the call fails. Scored events record `scoring_method: "llm" | "keyword"`.
- Extended event schema stored in `data/world_updates.json`, backward compatible: old
  events without the new fields are treated as keyword-scored with neutral framing.

## Section 3 — Per-Persona Belief Layer

**New module:** `engine/beliefs.py`.

**Persona state:** new `beliefs` field on each registry profile:

```json
"beliefs": {
  "economy":     {"shift": -0.04, "exposures": 7, "last_updated": "2026-06-11T09:00:00"},
  "immigration": {"shift": 0.02,  "exposures": 3, "last_updated": "2026-06-10T09:00:00"}
}
```

**Outlet families:** `fox_news, newsmax, oann, breitbart → right`;
`msnbc, npr, new_york_times, washington_post, cnn → left`;
`abc_news, nbc_news, cbs_news, local_tv, local_newspaper, bbc, the_hill, politico → mainstream`.

**Per update cycle, for each persona and each scored event:**
1. **Exposure:** probability the persona sees the story =
   `min(1.0, salience × (0.5 + 0.5 × |framing[family]|))` — outlet families cover stories
   they frame strongly more heavily, and high-salience stories reach everyone regardless
   of outlet. Seeded RNG (seed = update_id + profile_id) for reproducibility.
2. **Update:** `delta = direction × salience × framing[family] × susceptibility × BASE_RATE`.
   - `BASE_RATE` ≈ 0.01 per exposure (same order as today's per-headline shift).
   - **Confirmation bias:** topic-level party alignment comes from the existing
     `PARTY_VALENCE` matrix in `api/world_updates.py` (moved into the beliefs module).
     If the event's direction contradicts the persona's party's valence for that topic,
     susceptibility ×0.4. Independents and leaners get full susceptibility; strong
     partisans ×0.7 even for congenial news.
3. **Bounds:** each topic's cumulative shift is clamped to ±0.15 from zero (zero = the
   persona's CES-grounded baseline). Personas evolve; they do not become different people.
4. **Decay:** exponential decay toward zero with a 14-day half-life, computed from elapsed
   time since `last_updated` at the start of each cycle. Quiet news ⇒ beliefs revert.
5. **Audit trail:** every applied delta appends to the persona's `drift_log`:
   `{"date", "topic", "delta", "update_id", "shift_after"}`.

**Opinion engine change (`engine/opinion.py`):** `get_opinion` accepts the persona's
`beliefs`. For a question matched to topic T, the persona's own `beliefs[T].shift` is
applied to the KNN yes-probability (then renormalized) — replacing the flat party-level
`world_shifts`. The party-level path remains only as fallback for profiles without a
`beliefs` field (e.g., old snapshots).

## Section 4 — Update Cycle and Hooks

**New endpoint:** `POST /api/world-updates/cycle` runs the full pipeline:
fetch headlines → score (LLM or fallback) → apply decay → apply exposures/updates to all
personas → persist registry → run calibration check → return a summary report
(events processed, scoring method, mean shift by topic and party, calibration verdict).

**Scheduling:** `run_update_cycle.py` CLI wrapper + `update.bat` (project convention:
background processes use .bat), schedulable with Windows Task Scheduler. Intended cadence:
daily or every few days; the decay math is time-based so irregular cadence is safe.

**UI (Events tab):**
- "Run Update Cycle" button with summary display.
- Population drift chart: mean belief shift per topic over time (history kept in
  `data/belief_history.json`, one aggregate row per cycle).
- Calibration status badge (pass / drift warning / stale benchmarks).

## Section 5 — Calibration Gate (Viability)

**New module:** `engine/calibration.py`, invoked at the end of every update cycle.

- Re-runs anchor benchmarks (Trump approval, economy direction — the curated questions in
  `data/benchmarks.json`) through the opinion engine with current beliefs applied.
- Compares to the stored real-poll values. **Real values are entered manually** (refreshed
  by the user from 538/RCP); the system never scrapes or guesses them.
- **Verdicts:**
  - `pass`: MAE ≤ 0.05 on all anchors.
  - `drift_warning`: MAE > 0.05 on any anchor → apply a global dampening factor
    (multiply every persona's every topic shift by 0.5), re-check, log, and flag in UI.
    Dampening is recorded in each persona's `drift_log` as a `calibration_dampening` entry.
  - `stale`: any anchor's real value is older than 30 days → no pass/fail claim; UI badge
    says "refresh benchmarks". Dampening is not applied on stale data.
- Calibration history appended to `data/calibration_results.json`.

## Section 6 — User Guide and Walkthrough Page

**New page:** `static/guide.html`, linked from the app's main navigation ("Guide"). A
standalone page (not an 8th SPA view — keeps `app.js` lean), reusing `styles.css`, the
shared base CSS, and the chat widget so users can ask questions about the docs in place.

**Content (anchored sections, with a sticky table of contents):**

1. **How it works** — plain-language explanation of the whole system: real CES
   respondents → balanced persona sampling → KNN opinion matching → belief layer →
   calibration. One architecture diagram (static SVG/HTML, no JS dependencies).
2. **Walkthrough: run a poll** — step-by-step with screenshots/illustrations of the Poll
   tab: ask a question, what "CES coverage" means, why some questions are blocked,
   reading results and breakdowns.
3. **Walkthrough: update the population (news cycle)** — what an update cycle does,
   running it from the Events tab button or `update.bat`, scheduling it with Windows Task
   Scheduler, reading the drift chart and per-persona drift_log.
4. **Walkthrough: increase the population** — running
   `python build_population.py --target-n N`, reading the distribution report, what the
   ±3% balance gate means, backup/restore of the registry.
5. **Walkthrough: keep it calibrated** — refreshing real benchmark numbers in the
   Benchmark tab, what pass / drift warning / stale badges mean, what dampening does.
6. **Other operations** — snapshots and backtesting, filtering polls by demographics,
   toggling individual world updates, where the data files live and what each one is.
7. **FAQ / limitations** — uncovered topics (abortion, gun control), why opinions are
   bounded, real-data-only policy.

**Live stats:** the page header shows current population size, archetype count, last
update cycle, and calibration status via existing REST endpoints (one small inline
script; no framework). If the server is unreachable the page still renders fully as
static documentation.

## Section 7 — Testing and Error Handling

TDD throughout (tests written alongside each module):

- **Builder:** sampled distribution within ±3% of every marginal target; registry backup
  created; nonzero exit without write on failed balance; `ces_row_id` present.
- **Scoring:** LLM response parsing, malformed-JSON fallback, keyword fallback when key
  absent; schema backward compatibility for old events.
- **Beliefs:** decay math against closed-form half-life values; bounds clamping;
  confirmation-bias multipliers; seeded exposure determinism; drift_log entries.
- **Calibration:** dampening applied exactly once per warning; stale detection; history
  logging.
- **Integration:** full cycle against fixture headlines and a small fixture registry with
  network and LLM mocked — no test touches the network or an API key.
- **Guide page:** served at `/guide.html`; all walkthrough anchors present; stats script
  degrades gracefully when API endpoints are unreachable.

**Error handling:** RSS feed failure → skip feed, continue; LLM failure → keyword
fallback; registry write is atomic (write temp, rename) with timestamped backup;
corrupt `beliefs` field on a profile → reset that profile's beliefs to empty and log.

## Build Order

Each phase is independently shippable:

1. Population scale-up (Section 1)
2. LLM news scoring with fallback (Section 2)
3. Belief layer + opinion engine wiring (Section 3)
4. Cycle endpoint, CLI/bat, UI (Section 4)
5. Calibration gate (Section 5)
6. User guide page (Section 6) — written last so walkthroughs describe shipped behavior

## Out of Scope

- Abortion / gun-control question coverage (CES 2024 data-shape limitations, separate effort).
- International populations, multi-model ensembling.
- Automated scraping of real benchmark poll numbers.
- Per-persona LLM calls during updates (cost; one batched call per cycle only).
