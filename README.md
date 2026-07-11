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

**Stage 4 — Reusable Monthly ETL Pipeline (implemented, not yet
reviewed/merged).** A read-only BigQuery metadata validator (Stage 2),
the original January-2025-only prototype (Stage 3, committed/pushed,
tag `stage3-complete`), and a generalized CLI that runs the same
extract-join-validate-load pipeline for any valid month (Stage 4) now
exist. See `PROJECT_PLAN.md` for the full staged roadmap and `TASKS.md`
for the current backlog.

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

Four runnable entry points exist so far, all read-only except where noted:

- `scripts/validate_source_metadata.py` (Stage 2) — validates the two
  provided source tables' metadata against verified Stage 1 findings.
  Read-only.
- `scripts/run_monthly_pipeline.py --year YYYY --month MM` (Stage 4) —
  the general-purpose pipeline. Loads a one-month join of the full Citi
  Bike shape and curated weather fields into **your own** destination
  BigQuery project/dataset as `citibike_weather_monthly_YYYY_MM` via an
  idempotent `CREATE OR REPLACE TABLE`, then re-reads both source and
  destination tables to run the V1–V11 validation suite and prints a
  PASS/FAIL report (matched/unmatched/match-rate included). Supports
  `--dry-run` (builds and validates the SQL, reports a live bytes-processed
  estimate, writes nothing) and `--validate-only` (re-validates an
  existing destination table without replacing it) — the two are
  mutually exclusive. See `src/pipeline/monthly_pipeline.py` for the
  full exit-code table (0 success, 1 unexpected error, 2 CLI usage
  error, 3 configuration error, 4 invalid/unavailable month, 5
  authentication/query error, 6 load error, 7 validation failure).
  Availability is determined live from both source tables' current
  date ranges (never a hardcoded constant, never wall-clock "today");
  a requested month must be FULLY covered by both sources or it's
  rejected, not truncated.
- `scripts/run_prototype_january_2025.py` (Stage 3, preserved as a thin
  compatibility wrapper around the same pipeline, fixed to January 2025)
  — writes to the original `citibike_weather_prototype_2025_01` table,
  kept separate from anything the general Stage 4 CLI produces.
- `scripts/run_batch_pipeline.py --start-year YYYY --start-month MM --end-year YYYY --end-month MM` (Stage 5) — runs the SAME Stage 4
  pipeline once per month across a range, after a STRICT whole-range
  preflight check (every requested month must be fully covered by the
  live shared source range, or nothing runs — this returns exit code 4,
  the same code Stage 4 uses for a single invalid/unavailable month). By
  default stops at the first month that fails; pass `--continue-on-error`
  to process every requested month regardless — the returned code is
  then the FIRST failed month's own code, in chronological order.
  Supports the same `--dry-run` / `--validate-only` modes, applied to
  every month; `--dry-run`'s bytes-processed estimate is summed across
  the whole range. Writes a JSONL run log (`logs/batch_runs/`,
  gitignored): one `"month_run"` record per REQUESTED month (attempted
  or skipped) and exactly one final `"batch_summary"` record. See
  `src/pipeline/batch_pipeline.py` for the full exit-code table: 0
  success, 1 unexpected error, 2 CLI usage error, 3 configuration error,
  4 invalid/unavailable month or range, 5 authentication/query error, 6
  load error, 7 validation failure, 8 logging failure (the run log
  itself could not be written).

All four only ever write to the destination you configure below —
never to the `nyu-datasets` source project, and never by auto-creating
a dataset.

To run any of them:

1. Install Python 3.10+ and the dependencies in `requirements.txt`
   (`pip install -r requirements.txt`).
2. Authenticate with `gcloud auth application-default login`. This
   project uses Application Default Credentials only — service-account
   key files are not supported or referenced anywhere in this repo.
3. Set `GCP_PROJECT_ID` in your environment (your own billing/query
   project — see `config/.env.example`). `BQ_CITIBIKE_TABLE`,
   `BQ_WEATHER_TABLE`, and `BQ_LOCATION` all have verified defaults and
   don't need to be set unless you want to override them.
4. For the pipeline scripts (not `validate_source_metadata.py`): also
   set `BQ_DESTINATION_DATASET` to an **existing** dataset in your own
   project (required, no default — never auto-created);
   `BQ_DESTINATION_PROJECT_ID` is optional and defaults to
   `GCP_PROJECT_ID`.
5. Run whichever script(s) you need, e.g.
   `python scripts/run_monthly_pipeline.py --year 2025 --month 2 --dry-run`.

Unit tests (`python -m pytest` or `python -m pytest tests/unit`) require
no live BigQuery access and no credentials — they run entirely against
mocked/fake clients and in-memory fixtures. `pytest.ini` limits default
test discovery to `tests/unit`; the live-write checks
(`tests/integration/test_prototype_live.py`,
`tests/integration/test_monthly_pipeline_live.py`) are excluded by
default and must be run explicitly:
`RUN_LIVE_BIGQUERY_TESTS=1 python -m pytest tests/integration -m integration`.
