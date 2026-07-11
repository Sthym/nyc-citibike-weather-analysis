# Project Plan

This project is broken into small, reviewable stages. No stage begins
until the previous stage's acceptance criteria are met and the owner has
approved moving forward. No stage writes code that belongs to a later
stage (e.g., no dashboard code during extraction).

Legend: **Status** — Not started / In review / Approved / Done

---

## Stage 0 — Repository Foundation

**Status:** In review

**Objective:** Establish documentation, conventions, and folder structure
before any code is written.

**Deliverables:**
- `README.md`, `CLAUDE.md`, `PROJECT_PLAN.md`, `TASKS.md`, `DECISIONS.md`,
  `DATA_DICTIONARY.md`, `.gitignore`
- Full folder skeleton (see `README.md` structure table)
- `config/.env.example` (placeholders only)

**Acceptance criteria:**
- [ ] All required files exist and are reviewed/approved by the owner
- [ ] No ETL or dashboard code present anywhere in the repo
- [ ] No GCP project ID or credentials present anywhere in the repo
- [ ] Folder structure covers all eight anticipated areas: source-data
      investigation, extraction, transformation, BigQuery loading, SQL
      models, testing/validation, dashboard development, documentation

**Assumptions:** None finalized yet — see `DECISIONS.md` for open items
(GCP project, weather table source, language/tooling choices) to be
confirmed in later stages.

---

## Stage 1 — Source Data Investigation

**Status:** Not started

**Objective:** Understand the Citi Bike public trip-data structure and how
it has changed over ~13 years (2013–present), plus confirm the schema and
location of the provided daily weather table.

**Deliverables:**
- `docs/source_data_investigation/` notes cataloging every distinct schema
  version with its date range
- Documented file naming, format, and hosting conventions for source data
- Confirmed weather table schema, grain, and location
- Sample record counts per era

**Acceptance criteria:**
- [ ] Every distinct Citi Bike schema version is identified with an exact
      date range
- [ ] Weather table schema and grain are confirmed, or explicitly flagged
      as unresolved/blocked
- [ ] Findings are written to `docs/`, not left only in chat history

**Assumptions:** Citi Bike trip data is assumed to be publicly downloadable
as monthly files (to confirm in this stage).

---

## Stage 2 — Extraction

**Status:** Not started

**Objective:** Build scripts to download raw Citi Bike trip files for the
full historical range into `data/raw/` (or an equivalent raw landing area).

**Deliverables:**
- `src/extraction/` scripts
- An extraction run manifest/log (files downloaded, row/byte counts)

**Acceptance criteria:**
- [ ] Date range is configurable, not hardcoded
- [ ] Re-running extraction does not duplicate downloads (idempotent)
- [ ] Downloaded row/file counts match the source listing
- [ ] No credentials committed

---

## Stage 3 — Transformation / Schema Standardization

**Status:** Not started

**Objective:** Normalize every known schema version into one canonical
trip-level schema.

**Deliverables:**
- `src/transformation/` scripts
- Column-mapping documentation (old schema → canonical schema) in
  `DATA_DICTIONARY.md`

**Acceptance criteria:**
- [ ] Every known schema version is mapped to the canonical schema
- [ ] Data-quality checks pass: no unexpected nulls in required fields,
      valid trip durations, no full-row duplicates
- [ ] Transformation logic is documented and reproducible

---

## Stage 4 — BigQuery Loading

**Status:** Not started

**Objective:** Load standardized trip data into BigQuery raw/staging
tables.

**Deliverables:**
- `src/loading/` scripts
- `sql/schemas/` DDL definitions

**Acceptance criteria:**
- [ ] Loaded row counts match transformed row counts exactly, or a
      reconciliation is documented
- [ ] Partitioning/clustering strategy is decided and logged in
      `DECISIONS.md`
- [ ] No hardcoded project ID — config/env var only

---

## Stage 5 — SQL Models / Daily Summaries

**Status:** Not started

**Objective:** Build SQL models producing the daily-grain summary table
needed for the dashboard metrics.

**Deliverables:**
- `sql/models/staging/`, `sql/models/intermediate/`, `sql/models/marts/`

**Acceptance criteria:**
- [ ] Daily summary table has exactly one row per date with all required
      metrics
- [ ] Daily summary reconciles against raw trip counts

---

## Stage 6 — Weather Join

**Status:** Not started

**Objective:** Join daily ride summaries to the provided daily weather
table.

**Deliverables:**
- A `sql/models/marts/` model joining ride summary + weather table

**Acceptance criteria:**
- [ ] Join keys are documented and validated (date, and location if
      applicable)
- [ ] Join coverage is checked — % of days successfully joined; unmatched
      dates are logged
- [ ] Rain/dry and snow/no-snow thresholds are defined and documented in
      `DATA_DICTIONARY.md`

---

## Stage 7 — Testing & Data-Quality Framework

**Status:** Not started

**Objective:** Formalize automated data-quality checks across the
pipeline.

**Deliverables:**
- `tests/data_quality/` — row counts, date completeness, duplicates,
  missing values, invalid trip durations, weather-join integrity
- `tests/unit/` — transformation logic unit tests

**Acceptance criteria:**
- [ ] All checks are runnable via a single command
- [ ] Checks produce clear pass/fail output and are documented

---

## Stage 8 — Dashboard Development

**Status:** Not started

**Objective:** Build the public web dashboard on top of the BigQuery
marts.

**Deliverables:**
- `dashboard/` app code and deployment notes

**Acceptance criteria:**
- [ ] All 7 required metrics are represented (total rides/day, average
      trip duration, rides by user type, rides by weekday, rides by
      temperature range, rain vs. dry, snow vs. non-snow)
- [ ] No credentials or project IDs hardcoded in frontend code
