# Validation Study — Synthetic Population vs Real Polls

**Population:** 5,000 personas (ces-balanced-v2-5k) · **Protocol:** blind — synthetic distributions recorded (`data/validation_synthetic.json`, 10 runs each) **before** real numbers were looked up (`data/validation_real.json`). Deltas in `data/validation_report.json`.

Two rounds were run: **v1 (2026-06-12, original column registry)** exposed that most CES column mappings were wrong; after a full codebook verification against the authoritative CES 2024 guide (Harvard Dataverse doi:10.7910/DVN/X11EP6) and registry rebuild (`verify_ces_mappings.py`, 30/30 direction checks), **v2** was run blind again on the corrected engine.

## v2 results (corrected registry) — sorted by |Δ yes|

| CES column | Question | Synthetic yes | Real yes | Δ yes | Real source (quality) |
|---|---|---|---|---|---|
| CC24_410* | Trump job approval (vote proxy) | 39.2% | 40.0% | **−0.8** | RCP aggregate 06-05 (high) |
| CC24_328d | Repeal the ACA | 35.6% | 38.0% | **−2.4** | KFF 03-02 (medium) |
| CC24_326b | Renewable energy mandate | 71.6% | 65.0% | **+6.6** | Yale+Pew 04-26 (high) |
| CC24_323f | Forgive student loan debt | 62.7% | ~55% | +7.7 | Composite (low) |
| CC24_323d | Dreamers pathway to citizenship | 76.8% | 85.0% | −8.2 | Gallup 2025-06 (medium) |
| CC24_321c | Universal background checks | 96.2% | ~88% | +8.2 | Multi-poll consensus (medium) |
| CC24_323c | Build a border wall | 46.4% | 56.0% | −9.6 | Pew 2025-06 (high) |
| CC24_324a | Abortion as a matter of choice | 70.0% | 60.0% | +10.0 | Pew 2026-01 (high) |
| CC24_326a | EPA regulate CO2 | 69.6% | ~59% | +10.6 | Yale 04-26, framing caveat (low) |
| CC24_312b | Congress approval | 20.8% | 10.0% | +10.8 | Gallup 04-15 (high) |
| CC24_301 | Economy getting better | 31.9% | 20.0% | +11.8 | Gallup 05-17 (high) |
| CC24_302 | Household income increased | 20.4% | 34.0% | −13.6 | Gallup 04-15, wording caveat (medium) |
| CC24_323b | Increase border patrol | 76.5% | 59.0% | +17.5 | Gallup 2025-06 (medium) |
| CC24_308a_4 | Provide arms to Ukraine | 37.0% | 55.0% | −18.0 | YouGov 04-20 (high) |
| CC24_321a | Ban assault rifles | 70.9% | 52.0% | +18.9 | Gallup 2024-10 (high) |
| CC24_328e | Medicaid expansion | 84.5% | ~60% | +24.5 | KFF derived (medium) |

*\*No direct Trump-approval item exists in CES 2024 (fielded Nov 2024, Biden in office). The engine uses each neighbor's actual 2024 presidential vote as a documented proxy — and it lands within a point of the June 2026 RCP average.*

**Mean |Δ yes|: v1 ≈ 21 pts → v2 ≈ 11 pts.** The catastrophic 30–54 pt misses are gone; they were column-mapping bugs, now fixed and regression-guarded.

## What the population is GOOD at

1. **Identity-anchored political questions** — Trump approval (−0.8), ACA repeal (−2.4), renewables (+6.6), student debt (+7.7), Dreamers (−8.2), border wall (−9.6), abortion (+10.0). These are stable, party-sorted opinions where demographics + real survey microdata carry the signal. **This is the sweet spot for Polymarket-style culture/politics questions.**
2. **Direction and ordering** — even where the level is off, the synthetic population almost always gets the majority side and partisan ordering right.

## What it is WEAK at (and why)

1. **Fast-moving sentiment** (economy +11.8, Congress approval +10.8, border patrol +17.5): the CES baseline is frozen in Nov 2024. Real opinion moved. This is exactly what the belief-update layer is for, but its deliberate ±15 pt bound won't fully bridge 17–23 pt real-world swings. Expect the gap to shrink as update cycles accumulate; never expect it to vanish.
2. **Question-format artifacts:**
   - *Multi-select items* (Ukraine arms −18.0): CES "check all that apply" suppresses selection vs a direct support/oppose question. Treat CC24_308a numbers as floors.
   - *Wording gaps* (assault ban +18.9: CES "ban assault rifles" vs Gallup's much broader "ban semiautomatic guns"; household income −13.6: income vs "financial situation").
3. **Weak real-world reference points** (Medicaid expansion +24.5): no pollster fielded a direct national expansion question — the "real" number is itself a derived estimate. The miss may be substantially smaller than it looks.

## Coverage gained / lost in the registry fix

- **Gained (verified):** abortion (CC24_324), guns (CC24_321), Ukraine/foreign policy (CC24_308a), border wall, Medicaid expansion/work requirements, Biden & Harris & Congress approval, prices/inflation (CC24_303), household income (CC24_302), student debt $20k.
- **Lost (items never existed in CES 2024):** Medicare for All, $15 minimum wage, tax >$400k, deportation-increase, carbon tax. Questions on these now correctly return "not covered" instead of a wrong answer.

## Reproduce

```
python validation_study.py      # blind synthetic phase → data/validation_synthetic.json
# collect real numbers → data/validation_real.json (sources + quality tags)
python compare_validation.py    # deltas → data/validation_report.json
python verify_ces_mappings.py   # registry sanity: distributions + party cross-tabs
```
