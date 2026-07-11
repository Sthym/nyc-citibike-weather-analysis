# NYC Citi Bike & Weather Analysis

**GitHub repository name:** `msbai-dwd-st6076`

## Business question

How do temperature, rain, snow, seasonality, weekday, and rider type affect
daily Citi Bike ridership in New York City?

## Business goal

Build a reliable public dashboard that helps transportation planners, Citi
Bike operators, and the public understand how weather conditions affect
ridership patterns, so they can better anticipate demand, allocate bicycles,
plan station capacity, and prepare for weather-related changes in usage.

## Final dashboard metrics

- Total rides per day
- Average trip duration
- Rides by user type
- Rides by weekday
- Rides by temperature range
- Rides on rainy vs. dry days
- Rides on snowy vs. non-snowy days

## Technical goal

An end-to-end ETL pipeline that:

1. Extracts ~13 years of public Citi Bike trip data
2. Standardizes schemas that have changed over that period
3. Loads standardized data into BigQuery
4. Produces daily summary tables
5. Joins daily summaries to a provided daily weather table
6. Powers a public web dashboard

## Project status

**Stage 0 — Repository Foundation.** No extraction, transformation, loading,
or dashboard code exists yet. This stage only establishes documentation,
conventions, and folder structure. See `PROJECT_PLAN.md` for the full staged
roadmap and `TASKS.md` for the current backlog.

## Key project documents

| File | Purpose |
|---|---|
| `PROJECT_PLAN.md` | Staged roadmap (Stage 0–8), each with objective, deliverables, and acceptance criteria |
| `TASKS.md` | Task backlog, organized by stage, with status |
| `DECISIONS.md` | Architecture Decision Record (ADR) log — every material decision and assumption |
| `DATA_DICTIONARY.md` | Known and assumed schemas for source data, weather data, and pipeline outputs |
| `docs/source_data_profile.md` | Stage 1 investigation results: verified facts about the two provided BigQuery source tables and their join |
| `CLAUDE.md` | Working agreement for any AI agent (or human) contributing to this repo |

## Repository structure

| Path | Purpose | Supports |
|---|---|---|
| `data/raw/` | Untouched, as-downloaded source files (gitignored) | Extraction |
| `data/interim/` | Partially cleaned/standardized data (gitignored) | Transformation |
| `data/processed/` | Final local outputs ready for loading (gitignored) | Loading |
| `data/external/` | Small reference files safe to commit (e.g., station lists, schema samples) | Source-data investigation |
| `docs/source_data_investigation/` | Notes on Citi Bike schema versions, hosting, file formats over the 13-year range | Source-data investigation |
| `docs/architecture/` | Pipeline diagrams and design notes | Documentation |
| `docs/stage_reports/` | Evidence that a stage's acceptance criteria were met | Documentation |
| `src/extraction/` | Scripts that download raw Citi Bike trip data | Extraction |
| `src/transformation/` | Scripts that standardize changing schemas into one canonical schema | Transformation |
| `src/loading/` | Scripts that load standardized data into BigQuery | BigQuery loading |
| `src/utils/` | Shared helpers (config, logging, GCP auth) used across `src/` | All code stages |
| `sql/models/staging/` | 1:1 SQL views over raw BigQuery tables | SQL models |
| `sql/models/intermediate/` | SQL models combining/cleaning staging models | SQL models |
| `sql/models/marts/` | Final SQL models powering the dashboard (daily summaries + weather join) | SQL models |
| `sql/schemas/` | BigQuery table/view DDL definitions | BigQuery loading, SQL models |
| `tests/data_quality/` | Row counts, date completeness, duplicate, missing-value, invalid-duration, and weather-join checks | Testing and validation |
| `tests/unit/` | Unit tests for transformation logic | Testing and validation |
| `dashboard/` | Public web dashboard app (empty until Stage 8) | Dashboard development |
| `notebooks/` | Exploratory analysis, not part of the production pipeline | Source-data investigation, testing |
| `scripts/` | One-off or orchestration scripts (e.g., running the full pipeline) | All stages |
| `config/` | Config templates only — `.env.example` with placeholder values, never real secrets | All stages |

Every directory that has no files yet contains a `.gitkeep` placeholder so
the folder structure is preserved in Git before code is added.

## Assumptions

All assumptions are labeled and tracked in `DECISIONS.md` (entries marked
"Proposed — needs confirmation"). Two of the three original open items are
now confirmed by Stage 1 investigation (see `docs/source_data_profile.md`):

- ~~The ~13-year Citi Bike history is interpreted as program launch (2013)
  through the most recently available month.~~ **Confirmed:** the source
  table's exact range is 2013-06-01 through 2026-05-31. See `DECISIONS.md`
  D-004.
- ~~The "provided daily weather table" is assumed to be supplied or
  identified by the project owner.~~ **Confirmed:** the table is
  `nyu-datasets.weather.m_weather_daily_nyc`, verified as one record per
  date with no duplicates. See `DECISIONS.md` D-005.
- Python (ETL) and SQL (transformation models) are still assumed as the
  project's primary languages — not yet confirmed. See `DECISIONS.md`
  D-007.

Newer open items from Stage 1 investigation (see `DECISIONS.md` for full
detail): 10 missing Citi Bike calendar dates (D-011), 251 days of
rider-type reconciliation anomalies — most differences appear small but
some larger differences were also observed, full distribution not yet
documented (D-012) — and 24 confirmed missing dates in the weather table,
whose specific dates remain unresolved (D-016). None of these have an
assumed cause.

## Working agreement

- Work is broken into small, reviewable stages (`PROJECT_PLAN.md`).
- Nothing is committed, pushed, or merged without explicit owner approval.
- No GCP project IDs or credentials are ever hardcoded or committed —
  configuration is read from environment variables (see
  `config/.env.example`).
- Every stage has explicit acceptance criteria that must be met before it is
  marked done in `TASKS.md`.
- This GitHub repository — not chat history — is the persistent record of
  decisions and task status.

## Getting started

Not yet applicable — no runnable code exists in Stage 0. Setup instructions
(GCP project requirements, Python version, dependency installation) will be
added here once Stage 2 (Extraction) begins.
