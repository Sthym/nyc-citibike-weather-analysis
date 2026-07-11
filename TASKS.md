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

## Stage 3 — One-Month ETL Prototype (January 2025)

**Note on numbering:** This "Stage 3" follows the ad-hoc stage sequence
used in the actual implementation work (0 foundation, 1 source
investigation, 2 extraction foundation, 3 this one-month prototype), not
`PROJECT_PLAN.md`'s original Stage 3–6 breakdown (Transformation /
Loading / SQL Models / Weather Join), which predates the provided-dataset
pivot (D-009) and has not been renumbered or reconciled with this
sequence. This prototype's scope actually spans what `PROJECT_PLAN.md`
describes across its Stages 3–6, compressed into a single one-month
vertical slice. Reconciling the two numbering schemes is an open item —
not resolved in this update, and `PROJECT_PLAN.md` is left as-is here.

- [x] Add `pytest.ini` (`testpaths = tests/unit`, registers the
      `integration` marker) so a bare `pytest`/`python -m pytest` never
      collects the live integration test
- [x] Implement `src/transformation/prototype_query.py` — pure query
      builder: `month_range()` + parameterized (`@start_date`/`@end_date`)
      join SQL, full 15-column Citi Bike shape, 8 curated weather fields,
      `is_rainy`/`is_snowy` cast to `BOOL`, `weekday`, `weather_matched`
- [x] Implement `src/transformation/prototype_validator.py` — pure V1–V11
      validation logic; V8/V9 reclassified as source-quality findings,
      not failures (see `DECISIONS.md` D-019)
- [x] Implement `src/loading/prototype_loader.py` — idempotent
      `CREATE OR REPLACE TABLE` load, explicit destination
      project/dataset, no auto-creation, derived table name, query
      parameters for the date range
- [x] Implement `scripts/run_prototype_january_2025.py` — the only
      Stage 3 module that touches live BigQuery; loads the prototype,
      re-reads source + destination, runs validation, prints a PASS/FAIL
      report with matched/unmatched/match-rate
- [x] Add unit tests: `test_prototype_query.py`, `test_prototype_validator.py`
      (full V1–V11 coverage), `test_prototype_loader.py` — all mocked/fake,
      no network access
- [x] Add `tests/integration/test_prototype_live.py` — opt-in only via
      `RUN_LIVE_BIGQUERY_TESTS=1`, not run by default
- [x] Update `config/.env.example` with `BQ_DESTINATION_PROJECT_ID` /
      `BQ_DESTINATION_DATASET`
- [x] Log Stage 3 design decisions in `DECISIONS.md` (D-017–D-021)
- [x] Document the Stage 3 destination schema in `DATA_DICTIONARY.md`
      (Section 5a)
- [x] Run `python -m pytest tests/unit` locally — all passing
- [x] Owner review and approval of the Stage 3 prototype
- [x] Run `scripts/run_prototype_january_2025.py` against live BigQuery
      and record the observed PASS/FAIL result in `ENGINEERING_LOG.md`
- [x] Commit and push Stage 3 (tag: `stage3-complete`)

## Stage 4 — Reusable Monthly ETL Pipeline

- [x] Add `src/pipeline/month_period.py` — pure CLI-input parsing
      (`parse_year_month`), live-range-based month validation
      (`parse_month_period`, `compute_effective_range`), Stage 4
      destination naming (`monthly_table_name`), and the shared
      `load_destination_config` (moved out of the Stage 3 script so
      neither script imports the other)
- [x] Add `src/pipeline/monthly_pipeline.py` — the shared `execute()`
      orchestration (exit codes, dry-run, validate-only, full run),
      `gather_observed_data` (extracted from the Stage 3 script so
      full-run and `--validate-only` share one code path instead of
      duplicating query logic), and `estimate_bytes_processed` (live
      BigQuery dry-run for `--dry-run`'s bytes estimate)
- [x] Extend `src/loading/prototype_loader.py` with an optional
      `table_name` override (backward-compatible; Stage 3 callers
      unaffected) so Stage 4's `citibike_weather_monthly_*` naming and
      Stage 3's `citibike_weather_prototype_*` naming can share one
      loader
- [x] Add `scripts/run_monthly_pipeline.py` — the new reusable CLI
      (`--year`, `--month`, `--dry-run`, `--validate-only`)
- [x] Convert `scripts/run_prototype_january_2025.py` into a thin
      compatibility wrapper (NOT deleted) around
      `src.pipeline.monthly_pipeline.execute`, fixed to `year=2025,
      month=1`, preserving the original Stage 3 table name separately
- [x] Add unit tests: `test_month_period.py`, `test_monthly_pipeline.py`
      (all 8 exit-code paths), `test_run_monthly_pipeline_cli.py`
      (argparse-level usage errors and mutual exclusion), plus
      `TestTableNameOverride` in `test_prototype_loader.py` — all
      mocked/fake, no network access
- [x] Add `tests/integration/test_monthly_pipeline_live.py` — live
      source-range retrieval, `--dry-run`, and `--validate-only`; opt-in
      only via `RUN_LIVE_BIGQUERY_TESTS=1`; never calls `loader.load()`
- [x] Log Stage 4 design decisions in `DECISIONS.md` (D-022–D-024)
- [x] Run `python -m pytest` locally — all passing
- [ ] Owner review and approval of the Stage 4 pipeline
- [ ] Run `scripts/run_monthly_pipeline.py` against live BigQuery for at
      least one month other than January 2025, and record results in
      `ENGINEERING_LOG.md`
- [ ] Commit, push, and tag Stage 4 (only after approval)
- [ ] Run the full 2013–2026 historical range (explicitly out of scope
      for Stage 4 — see Stage 4 design constraints)
- [ ] Build the dashboard (explicitly out of scope for Stage 4)
- [ ] Create scheduled jobs (explicitly out of scope for Stage 4)

## Stage 3 (PROJECT_PLAN.md numbering) — Transformation / Schema Standardization (full historical range)

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
