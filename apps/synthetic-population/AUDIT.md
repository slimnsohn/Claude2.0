# Adversarial Integrity Audit — Synthetic Population Opinion Engine

Date: 2026-06-12 · Branch: `feat/living-population` (HEAD `92f63ea`, validation work through `28bfebd`)
Auditor stance: adversarial — actively tried to prove the system cheats. Excluded from scope: `api/polymarket.py` and `static/` (under concurrent edit by another agent; `static/guide.html` was read for disclosure checks only, findings flagged as observed-at-audit-time).

---

## 1. Scope & method

- Traced **every reader** of `data/benchmarks.json`, `data/calibration_history.json`, and `CURATED_BENCHMARKS` (grep across repo + full read of `engine/opinion.py`, `engine/beliefs.py`, `engine/calibration.py`, `engine/update_cycle.py`, `engine/news_scoring.py`, `engine/news_fetch.py`, `engine/ces_columns.py`, `engine/ces_loader.py`, `engine/integrity.py`, `engine/registry_io.py`, `engine/prompts.py`, `api/polls.py`, `api/benchmarks.py`, `api/world_updates.py`, `api/snapshots.py`, `api/events_api.py`, `snapshots/manager.py`, `generator/population_builder.py`, `generator/ces_harmonize.py`, `generator/archetypes.py`, `server.py`, `refresh_anchors.py`).
- Verified dampening math from code; checked for fitted/tuned constants (grep `curve_fit|minimize|GridSearch|optimi[sz]e|tune` — no hits in code).
- Verified the blind-validation protocol against **git commit timestamps and diffs** (`dcfff54` → `0dedcb1` → `492d785` → `28bfebd`).
- Ran `python -m pytest tests/ -q`: **469 passed, 1 failed** — the single failure is the known pre-existing `tests/test_api_polls.py::test_get_poll_after_aggregate_list_shows_headline` (KeyError `headline_result`). Nothing else failed.
- Ran `python verify_ces_mappings.py`: **30/30 direction checks PASS** against the raw 60k-row CES CSV.
- Ran two original adversarial experiments (archetype-ID consistency; negation phrasing) against the live registry — results below.

---

## 2. Out-of-sample integrity verdict: **CLEAN (engine path), with two caveats**

**Claim audited:** synthetic opinions derive only from CES 2024 microdata (KNN) + bounded news-derived belief shifts; real poll numbers never tune output except the disclosed 0.5× drift-dampening gate.

**All code paths that touch real poll numbers:**

| Reader | Use | Can it reach `get_opinion`/`get_distribution`? |
|---|---|---|
| `engine/calibration.py:24-50` | reads anchors from benchmarks.json / CURATED fallback | Only via the disclosed dampening gate (below) |
| `api/benchmarks.py:229-358` | display, and `compare` computes error metrics *after* synthetic run | No — `_run_synthetic` (188-222) never reads `real_results` |
| `api/world_updates.py:206-213` | reads `calibration_history.json` for a status badge | No — display only |
| `refresh_anchors.py` | *writes* real numbers into benchmarks.json | n/a |
| `engine/opinion.py` | **no import or read of any benchmark/real-poll data** — inputs are CES CSV, profile beliefs, and headline-derived `world_shifts` | — |

**Dampening math verified** (`engine/calibration.py:91-103, 130-136`): when any anchor MAE > 0.05 (line 132), `dampen_beliefs` does `b["shift"] = b["shift"] * 0.5` — a pure multiplicative shrink of the belief shift **toward zero, i.e. toward the raw CES baseline**. The real poll value appears only in the trigger condition, never in the update direction or magnitude. It mathematically cannot pull output toward the real number; it can only move output back toward the CES prior. The claim "stabilizer, not tuner" is accurate. (History check: `data/calibration_history.json` has 1 run, verdict `stale`, dampening has never actually fired.)

**No parameter fitting found.** All constants are round design numbers: `BELIEF_BOUND=0.15`, `BASE_RATE=0.01`, `HALF_LIFE_DAYS=14`, `MAE_THRESHOLD=0.05`, `DAMPENING_FACTOR=0.5`, legacy magnitude `0.01`, clamp `±0.10/±0.15`. No suspicious precision, no grid search, no optimization loop.

**Caveats:**

1. **The manual "send-to-Claude" poll path is not out-of-sample.** `api/polls.py:287-299, 487-552` lets an LLM answer poll prompts in persona (`engine/prompts.py` builds the prompt). The prompt contains no benchmark data, but the answering LLM knows real-world polling from training/context. Only the `auto-complete` (`ces_modeled`) path carries the out-of-sample guarantee. This distinction is recorded in results (`response_source: ces_modeled`) but should be kept in mind when consuming poll outputs.
2. **The gate is still a real-data feedback channel** — real numbers decide *when* shifts are halved. Disclosed and bounded (it only ever shrinks toward CES), but a purist should note population belief state is not 100% independent of benchmark data once dampening fires. It has not fired to date.

---

## 3. Lookahead verdict: **MOSTLY CLEAN — v1 blind verified by git; v2 blindness overstated; one backtesting design hazard**

**CURRENT_YEAR=2026 ages** (`generator/ces_harmonize.py:8`, `engine/ces_loader.py:52`): ages computed as `2026 − birthyr` — forward-aging real 2024 respondents to their current age. Backward-looking arithmetic, sane. Not prominently documented, but not lookahead.

**Belief updates / decay** (`engine/beliefs.py:87-98, 129-161`; `engine/update_cycle.py:52-100`): decay uses elapsed time from each belief's `last_updated` to the cycle `now`; exposure draws from live RSS headlines fetched *at cycle time*; drift_log entries are stamped with the cycle `now` and the cycle `update_id`. Exposure RNG is seeded `update_id:profile_id` (deterministic, replayable). No path reads future-dated data. Consistent.

**Snapshots** (`snapshots/manager.py`, `api/snapshots.py`):
- Immutability verified by `tests/test_temporal_isolation.py` (passes).
- **Design hazard (medium):** `create()` accepts an arbitrary user-supplied `date` (`api/snapshots.py:19-24`) but always snapshots the *current* registry; `load(filter_drift_after=date)` (`manager.py:50-61`) filters only the `drift_log` **audit trail** — it does **not** roll back `beliefs[*].shift`, which is what `get_distribution` actually consumes (`opinion.py:132-142`). A snapshot backdated to date D therefore answers polls using belief state that includes post-D events, while *looking* temporally clean because the visible drift_log was filtered. Currently no snapshots exist (`data/snapshots/manifest.json` is empty), so no contaminated backtest has been produced — but nothing prevents it. Backtesting results from backdated snapshots should not be trusted until shifts are reconstructed (e.g., by replaying drift_log deltas up to D).
- Minor: the date filter compares full ISO timestamps against a `YYYY-MM-DD` string (`"2026-06-12T08:00" <= "2026-06-12"` is False), silently excluding same-day entries; same issue in `create()`'s `events_applied_through` (`manager.py:29-34`).

**Validation protocol — commit evidence:**

| Commit | Time (2026-06-12) | Contents |
|---|---|---|
| `dcfff54` | 07:30:02 | v1 `validation_synthetic.json` + study script |
| `0dedcb1` | 07:38:22 | v1 `validation_real.json` + report + diagnosis |
| `492d785` | 07:55:17 | CES registry fix (code + tests + `verify_ces_mappings.py` only — no validation data touched) |
| `28bfebd` | 08:04:35 | **v2 synthetic + updated real + report in one commit** |

- **v1: blind protocol HOLDS by commit ordering** — synthetic recorded 8 minutes before real numbers entered the repo.
- **v2: the "blind" label is overstated.** Real numbers for ~10 of the 16 questions had been in the repo since 07:38; the registry fix (07:55) was made by an operator who had seen the v1 misses; and the v2 synthetic, the new real numbers, and the report were committed together — so commit ordering cannot establish that v2 synthetic was recorded before real numbers were known. The honest description of v2 is "post-fix re-evaluation," not a blind study. **Mitigation that keeps this out of cheating territory:** the registry fix is justified against an *independent* ground truth — the CES codebook plus 30 empirical partisan-direction checks (`verify_ces_mappings.py`, re-run during this audit: 30/30 PASS) — and the engine never programmatically reads the real numbers. The residual risk is human selection effect ("fix until it validates"), bounded by the codebook verification. The v2 mean error (~11 pts) should be treated as in-sample-adjacent, and the next genuinely blind round (new questions, synthetic committed first) is what should be believed.

**Trump-approval proxy (CC24_410):** using each neighbor's *actual Nov 2024 vote* to answer a June 2026 approval question is backward-looking — no lookahead. Disclosure status: documented in `engine/ces_columns.py:69-99` (extensive), `VALIDATION.md` (footnote), and the column display name string. **Not** surfaced at runtime: `engine/opinion.py:70` fetches `_col_name` but never includes it in the reasoning text (dead variable), and `api/benchmarks.py` responses omit the column name entirely — a consumer of `/api/benchmarks/run` or poll results sees "Trump job approval" answers with no proxy disclosure. Partially disclosed; should surface in API output.

---

## 4. Bias & bugs findings (severity-ranked)

### H1. Archetype-ID mismatch corrupts the main UI poll path (`api/polls.py:377-392`) — HIGH, verified empirically
`create_poll` builds **fresh** archetypes (`_build_archetypes`, min_cell_size=1) and stores prompts under fresh IDs; `auto_complete_poll` then indexes profiles by the **stale stored** `archetype_id` from the registry (assigned at population build time). These ID spaces do not agree:
- **Unfiltered poll, current 5k registry (measured):** 4,459/5,000 profiles change archetype_id on rebuild (140 fresh vs 128 stored cells). **26.3% of total poll weight** lands on fresh IDs with no stored profile → `profile = {}` → KNN encodes all demographics as unknown (−1) → an arbitrary corner of CES answers for them. A further **7.8% of weight** is answered by a representative of the **wrong party group**.
- **Filtered poll (measured):** `filters={"party_id":"rep"}` → **0/40** fresh prompt IDs exist among stored IDs → **100%** of "Republicans-only" responses are generated from empty profiles, i.e., one arbitrary non-Republican KNN neighborhood, silently reported as a complete poll.
- **Not affected:** the calibration gate (`engine/calibration.py:59-67`), `/api/benchmarks/run` (`api/benchmarks.py:188-196`), and therefore the validation study — these use the freshly built profiles consistently. **Consequence: the published validation numbers do NOT validate the UI poll (`auto-complete`) path.** Until fixed (index profiles by the freshly built archetype assignment, as benchmarks.py does), poll results from the UI — especially filtered ones — are unreliable.

### H2. Negation/polarity blindness in question matching (`engine/ces_columns.py:285-306`) — HIGH, verified, UNDISCLOSED
The keyword matcher ignores negation and answer polarity. Demonstrated live:
- "Do you **oppose** building a border wall?" → CC24_323c, returns the **support** distribution as "yes".
- "Do you **disapprove** of Trump's job performance?" → CC24_410, returns **approval** as "yes".
- "Should the US **stop** providing arms to Ukraine?" → CC24_308a_4 ("provide arms"), inverted.
For prediction-market phrasing (frequently negated: "Will X fail…", "oppose…", "below 40%…") this **inverts answers** with full confidence and no warning. Grep for "negation" across the repo: zero hits — the limitation is not disclosed in code comments, VALIDATION.md, guide, or TODO. Severity for the stated use case (Polymarket-style questions): high. Minimum fix: detect negation tokens and either flip interpretation or refuse to match.

### M1. Party composition bakes in unweighted CES partisan skew (`generator/population_builder.py:33-38`) — MEDIUM
`compute_targets` rakes party_id/urban to the **unweighted** CES sample distribution. Verified from `build_report.json`: Dem incl. leaners 49.2% vs Rep incl. leaners 35.6% (D+13.6). CES unweighted famously leans Dem relative to national party ID (CES ships `commonweight` to correct this; it is not used anywhere in the builder). This is disclosed as "CES-native distributions for party/urban" (design choice, no evidence of an outcome-flattering thumb), but the *consequence* is undisclosed: a structurally Dem-heavy population. The v2 validation deltas are consistent with it — the largest overshoots are all on the liberal side (assault ban +18.9, EPA +10.6, abortion +10.0, renewables +6.6, Medicaid expansion +24.5), while Trump approval (−0.8) is rescued by KNN conditioning on party. Recommend raking party to a current external party-ID benchmark or to CES weighted marginals.

### M2. Backdated-snapshot lookahead hazard (`snapshots/manager.py:50-61`) — MEDIUM
Covered in §3: drift_log filtering gives the appearance of temporal isolation but `beliefs.shift` is not rolled back. Theoretical today (no snapshots exist) but the API permits it silently.

### M3. `static/guide.html` documents the pre-fix (wrong) column registry — MEDIUM (doc-only; static/ under concurrent edit, observed at audit time)
The FAQ "How many topics does the engine actually cover?" (guide.html ~line 585-601) lists the **old, disproven** mappings: Trump approval = CC24_312i (actually **Harris** approval), Medicare-for-All/min-wage/$400k-tax coverage (items that don't exist in CES 2024), abortion/guns "not covered" (they are, post-`492d785`). A user trusting the guide would mis-trust coverage and could mis-read which proxy answers what. The guide also nowhere mentions the Trump-vote proxy.

### L1. Probability clamp after normalization (`engine/opinion.py:157-166`) — LOW
Normalize-then-clamp: a belief shift can drive `no_p` negative; after normalization the trio sums to 1 with a negative member, then clamping to 0 makes the sum exceed 1, slightly over-weighting yes/no vs unsure in the sampling roll. Bounded by ±0.15 shifts; distortion ≲ a few points in edge cases. Clamp before normalizing to fix.

### L2. `PARTY_VALENCE["crime"]` favors one party in both directions (`engine/news_scoring.py:103`) — LOW
`{"positive": "rep", "negative": "rep"}`: Republicans are never counter-aligned on crime news (full susceptibility both ways) while Democrats are always dampened (0.4×). This is the one remaining both-directions entry after the `914d06d` fix (which corrected healthcare/climate/gun_policy) and it is *not* covered by the explanatory comment added there. Mitigation: "crime" has no CES mapping (`engine/beliefs.py:30-40` documents inert topics), so it cannot affect opinion output — drift-chart cosmetics only. The confirmation-bias multipliers themselves are symmetric across parties (`beliefs.py:121-126`: 0.7 strong-partisan base, 0.4 counter, identical for dem/rep), and the keyword-fallback framing is 1.0 for every outlet family (`news_scoring.py:183`) — no hardcoded outlet advantage (LLM-scored framing is model-judgment, applied symmetrically).

### L3. Topic-blind legacy world-shift fallback (`engine/opinion.py:144-155`, `api/polls.py:84-102`) — LOW
For profiles without a belief shift on the matched topic, the engine applies the **sum of shifts from all active world updates regardless of topic** to any question. Bounded ±0.15, but it means an immigration headline can nudge a healthcare answer through the legacy path.

### L4. Stale balance report (`data/profiles/build_report.json`) — LOW
The report on disk is for the 500-profile batch (seed 7, `ces-balanced-v2-500`), while the live registry is the 5k batch (`ces-balanced-v2-5k`, 128 archetypes). The shipped population's own balance report (and its `max_gap`) is not persisted. The 500-batch `max_gap` is 0.03 — exactly at the gate tolerance (passes because the gate is strict `>`).

### L5. Curated benchmark mislabel (`api/benchmarks.py:111-117`) — COSMETIC
"Raising taxes on income over $400k" is categorized `foreign_policy` with a Gallup foreign-affairs URL. Display-only.

### Spot-check of interpret functions (5/5 consistent with verified codebook comments)
`_binary_support`, `_approval_4pt_correct` (low codes = approve, verified: 81% of Dems answer 1-2 on Biden), `_retro_5pt`, `_multiselect_selected`, `_trump_vote_proxy` (code 2 = Trump, verified 93% of R voters) — all match `engine/ces_columns.py` doc comments and the empirical 30/30 verification run.

---

## 5. Known disclosed limitations (as found in repo)

- Trump approval = 2024-vote proxy (ces_columns.py, VALIDATION.md — *not* surfaced in runtime API output).
- Belief shifts bounded ±0.15 with 14-day half-life decay toward CES baseline (beliefs.py docstring, guide FAQ).
- Calibration dampening 0.5× on drift_warning; "stale" >30 days = no verdict, no dampening (calibration.py docstring, guide).
- Benchmarks manually refreshed, never scraped (calibration.py, guide FAQ).
- Inert belief topics (crime, fiscal) accumulate but don't influence opinions (beliefs.py:30-33).
- CES baseline frozen at Nov 2024; fast-moving sentiment will lag (VALIDATION.md "weak at").
- Multi-select CES items are floors, wording-gap caveats per question (VALIDATION.md).
- Real-data-only persona policy (guide FAQ).

**Undisclosed limitations found:** negation blindness (H2); unweighted-CES party skew consequence (M1); snapshot belief-state lookahead (M2); proxy not surfaced at runtime; stale guide registry list (M3).

---

## 6. Overall verdict: **CLEAN-WITH-CAVEATS on integrity · ISSUES FOUND on correctness**

- **No cheating found.** Real poll numbers cannot reach opinion generation except through the disclosed dampening gate, whose math provably shrinks toward the CES baseline, never toward the poll value (and which has never yet fired). No fitted constants, no optimization against benchmarks. The v1 validation blind protocol is verifiable from git history.
- **Cheating-adjacent items, stated plainly:** (a) the v2 "blind" study label overstates — real targets were in-repo and known to the operator before the v2 run; treat v2's ~11-pt mean error as post-hoc until a fresh blind round on new questions; (b) the LLM "send-to-Claude" response path has no out-of-sample guarantee at all; (c) backdated snapshots would silently leak post-date belief state into "as-of" results.
- **For the intended use (prediction-market questions), the blockers are correctness, not honesty:** the archetype-ID mismatch (H1) makes UI auto-complete polls — and *all* filtered polls — quantifiably wrong today (26-34% of weight misattributed unfiltered; 100% on a party-filtered poll), and negation blindness (H2) can invert answers to market-phrased questions with no warning. Both must be fixed before relying on poll output; the benchmarks/calibration path is the only currently trustworthy query route, and only for affirmatively-phrased questions.
