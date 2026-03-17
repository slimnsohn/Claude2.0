# Synthetic Population Engine — Design Spec

**Date:** 2026-03-16
**Project:** `apps/synthetic-population/`
**Status:** Draft

---

## Purpose

Build a synthetic population engine that generates statistically realistic AI individuals from public census, survey, and demographic data. These individuals can be polled on any topic to simulate public opinion at scale, with two primary downstream uses:

1. **Prediction market edge** — Poll synthetic populations on Polymarket-relevant questions to identify consensus signals
2. **Complex topic reasoning** — Get grounded, demographically diverse perspectives on nuanced issues

## Design Decisions

- **Scale:** Start with ~1,000 profiles, built incrementally in batches of 50-100
- **LLM layer:** Claude Max (no API — manual or browser-automated querying)
- **Interaction:** CLI/scripts first, web UI later
- **Data approach:** Full academic pipeline (ACS PUMS + survey fusion), not shortcuts
- **Updates:** Periodic re-synthesis from new data + event-driven drift between releases
- **Architecture:** Provider-agnostic LLM layer (Claude Max now, swappable later)

---

## System Architecture

Four major components:

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Data Pipeline   │────▶│ Profile Generator │────▶│  Master Registry│
│  (ACS+CES+ANES  │     │  (batch creation, │     │  (JSON store,   │
│   +GSS+BRFSS    │     │   dedup, gap-fill)│     │   all profiles) │
│   +Pew+FINRA)   │     └──────────────────┘     └────────┬────────┘
└─────────────────┘                                       │
┌─────────────────┐     ┌──────────────────┐              │
│  Event Monitor   │────▶│  Opinion Engine   │◀────────────┘
│  (news → drift)  │     │  (archetype poll  │
└─────────────────┘     │   via Claude Max) │
                         └──────────────────┘
```

**Key principle:** The data pipeline and profile generator are pure Python with no LLM dependency. The LLM only enters at query time in the Opinion Engine. Profiles can be built and validated without touching Claude.

---

## Component 1: Data Pipeline

### Data Sources (Plugin Architecture)

Each source is a self-contained Python module implementing a standard interface:

```python
class DataSource(ABC):
    name: str
    variables_provided: list
    match_keys: list
    update_cycle: str  # "annual", "biennial", "election_year"

    def download(self) -> Path
    def clean(self, raw_path) -> DataFrame
    def harmonize(self, df) -> DataFrame
    def match_config(self) -> dict
```

**Standard schema:** Every source normalizes into a common demographic coding (age brackets, race categories, education levels, etc.). Source-specific variables pass through under a namespace prefix (e.g., `ces:gun_background_checks`, `anes:racial_resentment`).

**Adding a new source:**
1. Write one Python file implementing the `DataSource` interface (~100-200 lines)
2. Define variable mappings to the standard schema
3. Register in `registry.py`
4. Re-run fusion — pipeline picks it up automatically

### Source Registry

| Source | Layer | Records | Key Variables | Update Cycle |
|--------|-------|---------|--------------|-------------|
| ACS PUMS (5-yr) | Demographics | ~16M | Age, sex, race, education, income, occupation, marital status, geography, household structure, veteran, disability, citizenship, nativity | Annual (Dec) |
| CES | Political | ~60K | Party ID, ideology, vote choice, 30+ policy positions, validated turnout | Election + off-years |
| ANES | Psychology | ~8K | Racial resentment, authoritarianism, feeling thermometers, Big Five, political efficacy | Election years |
| GSS | Religion/Social | ~3K/wave | Religious affiliation/attendance, social trust, institutional confidence, gender roles, policy attitudes | Biennial |
| Pew ATP | Media/Science/Tech | 5-12K/wave | Media consumption, social media, tech use, vaccine attitudes, climate beliefs, science trust | 130+ waves |
| BRFSS | Health | 400K+/yr | Chronic conditions, insurance, exercise, tobacco, alcohol, mental health | Annual |
| CPS | Employment | 60K/mo | Detailed employment, union membership, gig work, income source, self-employment | Monthly |
| FINRA NFCS | Financial literacy | ~27K | Financial quiz scores, behaviors (retirement accounts, debt, tax approach, advisor use) | Every 3 years |
| Fed SCF | Wealth/Finance | ~6K | Investment types, financial planning, risk tolerance, wealth distribution | Triennial |

### Fusion Strategy

Layered statistical matching, each layer conditioned on previous:

1. **ACS PUMS** → demographic skeleton with real joint distributions
2. **CES** → political variables matched on age group + sex + race + education + income bracket + state + urban/rural
3. **ANES** → psychological variables matched on demographics + party ID
4. **GSS + Pew** → religion, social attitudes, media consumption, science opinions
5. **BRFSS** → health behaviors
6. **CPS** → employment detail, income source
7. **FINRA NFCS + Fed SCF** → financial literacy, investment behavior

Statistical matching via hot-deck or predictive mean matching (`StatMatch` or SDV conditional modeling). Final output: a fitted `GaussianCopulaSynthesizer` model saved to disk that encodes full correlation structure across all variables.

**Calibration:** IPF (Iterative Proportional Fitting) via `ipfr` to adjust synthetic population marginals to match known census totals (±2 percentage points for major categories).

---

## Component 2: Profile Generator & Master Registry

### Profile Schema (~148 fields)

**Core Demographics (15):** age, age_bracket, sex, race, education, marital_status, children_count, citizenship, veteran_status, disability, language, household_size, generation

**Socioeconomics (12):** income, income_bracket, employment_status, occupation, industry, union_membership, homeownership, housing_type, health_insurance, commute_mode, hours_worked, employer_size

**Economic Identity (10):** income_source (wages/self-employment/business/inheritance/investments/gig/retirement/disability), business_size, entrepreneurial_history, years_in_workforce, income_trajectory, class_self_identification, economic_mobility_perception, side_hustle, benefits_quality, job_security_perception

**Consumer/Financial Behavior (10):** risk_tolerance, debt_level, homeowner_equity, investment_types, brand_orientation, shopping_mode, car_ownership, streaming_services, credit_score_bracket, savings_months

**Financial Sophistication (8):** financial_literacy_score, financial_sophistication, tax_approach, retirement_strategy, uses_financial_advisor, insurance_coverage, financial_info_source, employer_match_awareness

**Geography (14):** state, puma, urban_rural, region, census_division, metro_area, county_type, congressional_district, border_state, climate_zone, local_economy_type, population_density, cost_of_living_area, time_zone

**Political Identity (10):** party_id (7-point), ideology (7-point), vote_2020, vote_2024, registration_status, political_interest, trust_in_government, political_efficacy, partisan_strength, swing_voter

**Policy Positions (15):** abortion, gun_control, immigration, climate_policy, healthcare_system, government_spending, trade_policy, criminal_justice, education_policy, social_security, marijuana, minimum_wage, foreign_policy, tax_policy, tech_regulation

**Psychology/Values (10):** racial_resentment, authoritarianism, social_trust, openness, conscientiousness, extraversion, agreeableness, neuroticism, institutional_confidence, meritocracy_belief

**Religion (5):** affiliation, denomination, attendance, biblical_literalism, religion_importance

**Media Diet (12):** primary_news_source, secondary_news_source, podcast_listener, podcast_type, social_media_primary, social_media_news, youtube_political, talk_radio, newspaper_reader, news_frequency, media_trust, info_ecosystem

**Science/Health Opinions (10):** vaccine_attitude, covid_vaccine_status, climate_change_belief, climate_policy_support, evolution_belief, gmo_attitude, trust_medical_establishment, trust_scientific_establishment, covid_lockdown_opinion, pharma_trust

**Origin/Mobility (5):** native_born, generation_if_immigrant, years_in_country, moved_for_work, hometown_vs_current

**System Metadata (6):** profile_id, batch_id, created_at, updated_at, archetype_id, backstory

### Batch Generation Flow

1. Run: `python generate.py --count 50`
2. Generator loads fitted synthesis model + current master registry
3. Draws candidate profiles from the model
4. **Dedup check** — composite key comparison (age bracket + sex + race + education + state + party ID + religion + income source). Reject candidates matching 6+ of 8 keys with any existing profile
5. **Gap analysis** — compare current population distribution against national ACS marginals. Bias sampling toward underrepresented cells
6. Generate natural-language backstories (template-based, ~10 variants per sentence slot, no LLM needed)
7. Assign archetype IDs via clustering
8. Append to master registry
9. Report: profiles added, current population demographics vs targets, gaps remaining

### Storage

- Master registry: `data/profiles/registry.json` — array of all profiles
- Individual profiles also queryable by archetype, batch, or demographic filters
- JSON format (v1), upgradeable to SQLite if performance requires it
- Generated data directory is gitignored

---

## Component 3: Archetype System & Opinion Engine

### Archetype Definition

Profiles clustered on the variables with highest opinion-predictive power:

- Party ID (3: Dem/Ind/Rep)
- Race (4: White/Black/Hispanic/Other)
- Education (2: College/No college)
- Religiosity (2: Regular attender/Not)
- Urban/Rural (2)
- Info ecosystem (3: Mainstream/Right-alternative/Left-alternative+Disengaged)

Theoretical maximum: 3×4×2×2×2×3 = **288 cells**, collapsing sparse cells yields **25-40 active archetypes**. Each archetype carries a population weight based on how many profiles it represents.

### Polling Flow

1. User poses a question (e.g., "Will the Fed cut rates in Q2 2026?")
2. Engine selects one representative profile per archetype (closest to centroid or random sample)
3. Constructs persona-conditioned prompts with conviction anchoring (see Opinion Integrity below)
4. Collects ~30 responses from Claude Max
5. Aggregates with demographic weighting
6. Outputs: weighted opinion distribution, confidence intervals, demographic breakdowns

### Opinion Integrity — No Groupthink

Three mechanisms enforce authentic, steel-headed responses:

**1. Conviction Anchoring (Prompt Design)**

System prompt explicitly instructs against hedging:
- If this person would have a strong opinion, express it strongly
- If they wouldn't care, say so bluntly
- If they'd be misinformed, reflect that — don't correct it
- Their media diet constrains their awareness of arguments
- No caveats or qualifiers unless this specific person genuinely would use them

**2. Calibration Score (Hedge Detection)**

Post-response heuristic check:
- Count hedge words ("however", "on the other hand", "both sides")
- Compare confidence to expected range for archetype × topic
- Flagged responses get re-queried with harder prompt: "You gave a balanced answer, but this person lives in [context]. What do they ACTUALLY think?"

**3. Opinion Persistence (Drift Log)**

Each profile's `drift_log` tracks past positions. When polled on related topics, prior opinions are included in prompt context. Engine flags contradictions — a profile that strongly opposed immigration last week shouldn't support open borders this week.

### Scaling Path

Current: 1 query per archetype (~30 Claude Max conversations per poll)
Future (with API): Poll all 1,000+ profiles individually. Aggregation math stays the same, just drop archetype weighting for direct per-profile voting.

---

## Component 4: Event Monitor & Drift System

### Event Ingestion

Events tagged with affected demographic segments and attitude deltas:

```json
{
  "event_id": "EVT-2026-0042",
  "date": "2026-03-15",
  "description": "Supreme Court rules 6-3 to restrict EPA authority",
  "affected_segments": {
    "party_id": {"republican": +0.1, "democrat": -0.15},
    "education": {"college": +0.05},
    "topic_area": "climate_policy"
  }
}
```

Manual event entry for v1. Automatable via news API ingestion later.

### Drift Tiers

| Tier | Variables | Drift Behavior |
|------|-----------|---------------|
| **Immutable** | Age, race, sex, education, veteran status, native_born | Never change (age increments annually) |
| **Slow-moving** | Party ID, religiosity, urban/rural, income bracket, financial sophistication | Only on full pipeline refresh or major life-event modeling |
| **Responsive** | Issue-specific attitudes, institutional confidence, candidate favorability, media trust | Adjusted by events, bounded by profile identity |

**Drift constraint:** Deltas are clamped relative to the profile's baseline. A strong Republican's climate attitude might shift from 0.3 to 0.4, never to 0.8. Identity bounds the range of movement.

### Polymarket Workflow

1. Market-relevant event occurs (debate, court ruling, economic report)
2. Tag event with affected segments
3. Drift propagates to affected profiles
4. Re-poll affected archetypes
5. Compare pre-event vs post-event polling → signal for prediction market movement

---

## Project Structure

```
apps/synthetic-population/
├── CLAUDE.md
├── TODO.md
├── start.bat
├── requirements.txt
│
├── pipeline/
│   ├── sources/
│   │   ├── base.py              # DataSource ABC + standard schema
│   │   ├── acs_pums.py
│   │   ├── ces.py
│   │   ├── anes.py
│   │   ├── gss.py
│   │   ├── pew_atp.py
│   │   ├── brfss.py
│   │   ├── cps.py
│   │   ├── finra_nfcs.py
│   │   └── fed_scf.py
│   ├── registry.py              # Active source tracking
│   ├── fuse.py                  # Statistical matching engine
│   ├── fit_model.py             # Train SDV synthesizer
│   └── calibrate.py             # IPF against census marginals
│
├── generator/
│   ├── generate.py              # CLI: --count N
│   ├── dedup.py                 # Composite-key uniqueness
│   ├── gap_analysis.py          # Pop vs marginal comparison
│   ├── backstory.py             # Template-based narratives
│   └── archetypes.py            # Clustering + assignment
│
├── engine/
│   ├── poll.py                  # Prompt construction + polling flow
│   ├── prompts.py               # Templates with conviction anchoring
│   ├── aggregate.py             # Weighted aggregation + CI
│   └── integrity.py             # Hedge detection, consistency checks
│
├── monitor/
│   ├── events.py                # Event ingestion + tagging
│   └── drift.py                 # Bounded drift application
│
├── data/                        # Generated data (gitignored)
│   ├── models/
│   ├── profiles/
│   ├── events/
│   └── polls/
│
└── tests/
    ├── test_pipeline.py
    ├── test_generator.py
    ├── test_engine.py
    └── test_monitor.py
```

Raw census/survey source data lives in workspace-level `data/raw/` per workspace conventions. Only generated outputs live inside the project.

---

## Tech Stack

- **Python** — all backend (pipeline, generator, engine, monitor)
- **Pandas** — data wrangling, cleaning, harmonization
- **SDV (Synthetic Data Vault)** — GaussianCopulaSynthesizer for correlation-preserving synthesis
- **StatMatch** (via rpy2) or custom predictive mean matching — cross-dataset fusion
- **JSON file storage** — profiles, events, poll results (v1)
- **Browser UI** — later phase, HTML/JS with chat widget per workspace conventions

## Validation Strategy

Three levels:

1. **Marginal validation** — one-way distributions of every variable vs known population statistics
2. **Correlation validation** — full correlation matrix comparison vs real survey data (Frobenius norm)
3. **Downstream validation** — logistic regression predicting vote choice on synthetic vs real data, compare coefficients

Propensity score mean-squared error (pMSE) as single summary statistic — values near zero = synthetic indistinguishable from real.

---

## Open Questions / Future Work

- Web UI design (phase 2)
- Automated Claude Max querying via browser automation
- News API integration for automated event ingestion
- Multi-model ensembling if API access becomes available
- International population expansion (non-US markets)
- Polymarket API integration for automated signal generation
