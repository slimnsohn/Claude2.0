# Odds Pipeline

## Overview
Multi-sport data layer: pulls closing odds from The Odds API + per-segment scores from official sport feeds. Hybrid storage (raw JSON archive + derived SQLite). Six sports: NBA, NFL, NHL, MLB, NCAAB, NCAAF.

## Tech Stack
Python 3.11+, SQLite, requests, sport-specific libraries (nba_api, nfl_data_py, MLB-StatsAPI, cfbd).

## Quick Start
```bash
start.bat
```

## Project Structure
- `odds_pipeline/odds_source/` — The Odds API client + ingest
- `odds_pipeline/results_sources/` — One adapter per sport
- `odds_pipeline/store/` — SQLite schema + derive (raw -> tables)
- `odds_pipeline/identity/` — Cross-source game-ID matching, team aliases
- `data/raw/` — Immutable JSON archive
- `data/odds_pipeline.db` — Derived working database

## Environment Variables
- `THE_ODDS_API_KEY` — required for odds pulls
- `CFBD_API_KEY` — required for NCAAF results
