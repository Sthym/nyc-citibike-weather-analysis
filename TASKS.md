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

- [x] Design and implement a read-only BigQuery extraction foundation
      (`src/extraction/`): table-ID validation, config loading (ADC only,
      no service-account keys), a read-only client wrapper, and metadata
      validation against verified Stage 1 findings
- [x] Add `scripts/validate_source_metadata.py` as the single entry point
      that touches live BigQuery
- [x] Add unit tests for all of the above (`tests/unit/test_table_id.py`,
      `test_config.py`, `test_bigquery_client.py`,
      `test_metadata_validator.py`) — all mocked, no network access
- [x] Add `requirements.txt`
- [ ] Owner review and approval of the Stage 2 extraction foundation
- [ ] Commit and push Stage 2 foundation (only after approval)
- [ ] Design extraction script interface (configurable date range) —
      *revisit: source is a provided BigQuery table, not files to
      download; scope may be much smaller than originally planned (see
      DECISIONS.md D-009)*
- [ ] Implement download logic for all known Citi Bike file formats —
      *likely not applicable; see above*
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
