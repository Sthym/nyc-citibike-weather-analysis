# Tasks

Task backlog, organized by stage. Mirrors `PROJECT_PLAN.md`. Update this
file — not chat history — as the source of truth for status.

Legend: `[ ]` not started · `[~]` in progress · `[x]` done

---

## Stage 0 — Repository Foundation

- [x] Draft `README.md`
- [x] Draft `CLAUDE.md`
- [x] Draft `PROJECT_PLAN.md`
- [x] Draft `TASKS.md`
- [x] Draft `DECISIONS.md`
- [x] Draft `DATA_DICTIONARY.md`
- [x] Draft `.gitignore`
- [x] Create folder skeleton with `.gitkeep` placeholders
- [x] Create `config/.env.example` (placeholders only)
- [ ] Owner review and approval of all Stage 0 deliverables
- [ ] Commit and push Stage 0 (only after approval)

## Stage 1 — Source Data Investigation

- [ ] Identify Citi Bike hosting location and file/naming conventions
- [ ] Catalog every distinct trip-data schema version with date ranges
- [ ] Document known column renames/removals (e.g., pre-2021 vs. post-2021
      fields)
- [ ] Confirm schema, grain, and location of the provided weather table
- [ ] Pull sample record counts per schema era
- [ ] Write findings to `docs/source_data_investigation/`

## Stage 2 — Extraction

- [ ] Design extraction script interface (configurable date range)
- [ ] Implement download logic for all known Citi Bike file formats
- [ ] Add idempotency (safe re-runs, no duplicate downloads)
- [ ] Log an extraction manifest (files, row/byte counts)
- [ ] Verify counts against source listing

## Stage 3 — Transformation / Schema Standardization

- [ ] Define canonical trip-level schema in `DATA_DICTIONARY.md`
- [ ] Implement mapping for each known source schema version
- [ ] Add data-quality checks: required-field nulls, valid durations,
      duplicate rows
- [ ] Document transformation logic

## Stage 4 — BigQuery Loading

- [ ] Define raw/staging table DDL in `sql/schemas/`
- [ ] Implement load scripts in `src/loading/`
- [ ] Decide and document partitioning/clustering strategy
- [ ] Reconcile loaded vs. transformed row counts

## Stage 5 — SQL Models / Daily Summaries

- [ ] Build staging models (1:1 over raw tables)
- [ ] Build intermediate models
- [ ] Build daily-summary mart
- [ ] Reconcile daily summary against raw trip counts

## Stage 6 — Weather Join

- [ ] Validate join keys against the weather table
- [ ] Build the ride-summary + weather join model
- [ ] Measure and log join coverage / unmatched dates
- [ ] Define rain/dry and snow/no-snow thresholds

## Stage 7 — Testing & Data-Quality Framework

- [ ] Row-count checks
- [ ] Date-completeness checks
- [ ] Duplicate checks
- [ ] Missing-value checks
- [ ] Invalid trip-duration checks
- [ ] Weather-join integrity checks
- [ ] Unit tests for transformation logic
- [ ] Single-command test runner

## Stage 8 — Dashboard Development

- [ ] Choose dashboard framework/hosting (log decision in `DECISIONS.md`)
- [ ] Implement all 7 required metrics
- [ ] Confirm no credentials/project IDs in frontend code
- [ ] Deployment notes
