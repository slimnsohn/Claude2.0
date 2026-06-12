# Validation Study v1 — Synthetic Population vs Real Polls

**Date:** 2026-06-12 · **Population:** 5,000 personas (ces-balanced-v2-5k) · **Protocol:** blind — all synthetic distributions were recorded (`data/validation_synthetic.json`, 10 runs each) **before** any real numbers were looked up (`data/validation_real.json`).

## Headline results (sorted by |Δ yes|)

| CES column | Question | Synthetic yes | Real yes | Δ yes | Real source (date) | Verdict |
|---|---|---|---|---|---|---|
| CC24_312i | Trump job approval | 41.2% | 40.0% | **+1.2** | RCP aggregate (06-05) | ✅ Excellent |
| CC24_300_3 | Increase deportations | 34.6% | 38.0% | **−3.4** | AP-NORC (2025-04) | ✅ Good |
| CC24_415c | Carbon tax on fossil fuels | 54.9% | 59.0% | **−4.1** | Yale CCAM (04-26) | ✅ Good |
| CC24_301 | Economy getting better | 28.6% | 20.0% | +8.6 | Gallup (05-17) | ⚠️ Fair |
| CC24_326b | Medicare for All | 71.4% | 59.0% | +12.4 | YouGov (2025-07) | ⚠️ Fair |
| CC24_415d | Renewable energy mandate | 52.1% | 65.0% | −12.9 | Yale + Pew (04-26) | ⚠️ Fair |
| CC24_308a_2 | $15 minimum wage | 53.7% | 69.0% | −15.3 | YouGov (2025-11) | ❌ Poor |
| CC24_308a_4 | Tax income >$400k | 35.6% | 58.0% | −22.3 | Pew (2025-02) | ❌ Poor |
| CC24_300_1 | Increase border patrol | 81.8% | 59.0% | +22.8 | Gallup (2025-06) | ❌ Poor |
| CC24_300_2 | DREAMers legal status | 56.8% | 85.0% | −28.2 | Gallup (2025-06) | ❌ Poor |
| CC24_308a_5 | Forgive student debt $50k | 25.5% | ~55% (±10) | −29.5 | Composite, low conf. | ❌ Poor |
| CC24_326a | Repeal ACA | 70.2% | 38.0% | +32.2 | KFF proxy (03-02) | ❌ Bad |
| CC24_311a | Congress approval | 49.1% | 10.0% | +39.1 | Gallup (04-15) | ❌ Bad |
| CC24_303 | Personal finances better | 88.2% | 34.0% | +54.2 | Gallup (04-15) | ❌ Bad |

## Diagnosis — the misses are mostly **column-mapping bugs, not population bugs**

Raw CES 2024 value distributions and party cross-tabs (`diagnose_columns.py`) show that several columns in `engine/ces_columns.py` are mislabeled or sign-flipped:

- **CC24_326a** ("Repeal ACA"): 92% of Democrats give answer 1. Value 1 cannot mean "support repeal" — either the coding is inverted or this column is a different (Democratic-favored) proposal entirely.
- **CC24_303** ("Personal finances better"): 76% of Republicans give answer 1 — under the November-2024 Biden economy. Value 1 is almost certainly a *negative* answer (coding inverted).
- **CC24_311a** ("Congress approval"): the raw shape (2% at value 1, 48% at value 3) doesn't fit the assumed 4-point approval coding; ~49% "approval" is implausible against Gallup's long-run 10–20% range.
- **CC24_308a_4 / _5** (tax >$400k, student debt): Democratic support of only 55% / ~25% is far below every real poll; likely mislabeled grid items or inverted coding.

**Action (Task 13): verify every column against the actual CES 2024 codebook and fix `ces_columns.py`, then rerun this study.** Until then, treat results on the flagged columns as unreliable.

## Genuine signal — what the population is **good at**

- **Presidential approval (Δ +1.2)** — the architecture's best case: stable question wording, CES coding likely correct, demographics drive the answer. This survived 19 months of real-world drift from the Nov-2024 CES field date.
- **Deportation support (Δ −3.4)** and **carbon tax (Δ −4.1)** — both excellent on the support side.
- **Economy direction (Δ +8.6)** — decent given the CES snapshot is frozen in Nov 2024; this is exactly the gap the belief layer is designed to close over repeated update cycles.

## Structural limitations (not bugs)

1. **Temporal drift beyond the belief bound:** border-patrol support really fell 76%→59% between mid-2024 and mid-2025. The CES baseline holds the old number, and the belief layer's ±15-point bound (deliberate) can't fully bridge a 23-point real-world swing.
2. **Question-wording effects:** Gallup's generous DREAMers framing ("chance to become citizens if they meet requirements over time") polls ~28 points above the CES grid item. Synthetic-vs-real comparisons are only as good as the wording match.
3. **No "unsure" in CES binary grids:** CES forces support/oppose, real polls have 5–34% unsure. Full-distribution MAE is structurally inflated for grid questions; Δ yes is the better metric.
4. **Real-data quality varies:** some "real" numbers are estimated residuals or composites (marked medium/low quality in `data/validation_real.json`).

## Calibration anchors refreshed

`data/benchmarks.json` anchors updated with fresh numbers (Trump approval 40/57/3, RCP 2026-06-05; economy 20/76/4, Gallup 2026-05-17), so the calibration gate now evaluates against current reality instead of reporting "stale".

## Files

- `validation_study.py` — re-runnable blind synthetic phase
- `compare_validation.py` — delta computation → `data/validation_report.json`
- `diagnose_columns.py` — raw CES distribution checks
- `refresh_anchors.py` — anchor refresh helper
