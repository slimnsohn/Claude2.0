# TODO — Synthetic Population Engine

> Update manually. This file persists across sessions.

## Now

- [ ] Download real ACS PUMS data and run first batch generation
- [ ] Test with real CES data (Harvard Dataverse access)

## Next

- [ ] Build web UI for population browsing and polling
- [ ] Automate Claude Max querying via browser automation
- [ ] News API integration for automated event ingestion

## Backlog

- [ ] Polymarket API integration for automated signal generation
- [ ] International population expansion (non-US markets)
- [ ] Multi-model ensembling if API access becomes available
- [ ] Migrate from pickle to SDV save_to_json for model persistence

## Done

- [x] Project scaffolding (schema, pipeline, generator, engine, monitor packages)
- [x] Standard schema with 143 variables across 14 categories + validation
- [x] DataSource ABC with harmonize and plugin interface
- [x] Source registry for plugin discovery
- [x] ACS PUMS source plugin with demographic harmonization
- [x] CES source plugin with political variables
- [x] 7 remaining source plugins (ANES, GSS, Pew ATP, BRFSS, CPS, FINRA, Fed SCF)
- [x] Statistical fusion engine with KDTree nearest-neighbor matching
- [x] SDV GaussianCopulaSynthesizer model trainer
- [x] IPF calibration against census marginals
- [x] Composite-key deduplication checker
- [x] Gap analysis with priority sampling weights
- [x] Template-based backstory generator
- [x] Archetype clustering with categorical cross-tab
- [x] Profile generator CLI with batch creation
- [x] Poll prompt templates with conviction anchoring
- [x] Hedge detection and opinion consistency checks
- [x] Weighted poll aggregation with bootstrap CIs
- [x] Full polling flow (prepare, record, aggregate)
- [x] Event ingestion and storage
- [x] Bounded drift engine with immutable variable protection
- [x] Full pipeline integration smoke test (270 tests passing)
