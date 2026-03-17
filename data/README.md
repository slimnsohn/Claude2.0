# data/ — External Source Data

This folder is **only** for externally sourced data: datasets downloaded from third parties, CSVs collected from outside sources, reference data that would be painful or impossible to recreate.

Projects that generate, download, or scrape their own data keep it locally in their own folder (e.g. `apps/my-project/data/`).

## Structure

```
data/
├── raw/              ← Original external files, never modified after drop
├── processed/        ← Cleaned/transformed versions of raw, reference quality
└── _pipelines/       ← Scripts that transform raw → processed
```

Each has topic subdirectories (e.g. `polymarket/`, `sports/`, `real-estate/`). Add new topics as needed.

## Flow: raw → pipeline → processed

1. **Drop** external data into `raw/{topic}/`. Never edit it after.
2. **Write a pipeline** in `_pipelines/{topic}/` that reads from raw, transforms, and writes to processed.
3. **Output** lands in `processed/{topic}/`. This is the reference library other projects read from.

Every file in `processed/` is fully traceable back to its raw source through a pipeline script.

## Naming Conventions

- **raw/** — Include source and date: `polymarket-wallets-2025-03-14-export.json`
- **processed/** — Include version or date range: `wallet-clusters-v2.json`, `ncaab-stats-2018-2022.csv`
- **_pipelines/** — Name scripts after what they produce: `build-wallet-clusters.py`

## Decision Guide: Where Does Data Go?

| Question | Answer |
|----------|--------|
| Did I find this externally and want to preserve it? | `data/raw/` |
| Would it be painful or impossible to get again? | `data/raw/` |
| Does a project generate or download it on its own? | Stays in the project folder |
| Is it from a free, fast API the project can call anytime? | Stays in the project folder |
| Not sure? | Start in the project folder. Promote to `data/` only if it's valuable enough to preserve. |

## Rules

- `raw/` is **immutable**. Files go in, never get edited or deleted.
- `_pipelines/` is the **only** thing that writes to `processed/`.
- Data files use JSON or CSV. No proprietary formats.
- Projects stay self-contained — don't put project-generated data here.
