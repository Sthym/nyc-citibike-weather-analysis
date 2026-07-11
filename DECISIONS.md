# Decisions

Architecture Decision Record (ADR) log. Every material decision and every
assumption made in the absence of explicit direction is recorded here,
newest last. This file — not chat history — is the persistent record.

Status values: **Proposed** (needs confirmation) · **Accepted** ·
**Confirmed** · **Superseded** (link to the replacing entry)

---

### D-001 — Use this GitHub repository as persistent project memory
**Status:** Accepted
**Context:** The project spans many stages and potentially many sessions
with different contributors (human or AI). Chat history is not durable or
shared.
**Decision:** All decisions, task status, and stage progress are recorded
in this repo (`DECISIONS.md`, `TASKS.md`, `PROJECT_PLAN.md`,
`docs/stage_reports/`), not solely in chat.

### D-002 — No GCP project ID or credentials committed
**Status:** Accepted
**Context:** Explicit project requirement.
**Decision:** All GCP configuration (project ID, dataset names, service
account paths) is read from environment variables. `config/.env.example`
documents the expected variables with placeholder values only. Real values
live in a local, gitignored `.env`.

### D-003 — Nine-stage roadmap, each requiring explicit approval
**Status:** Accepted
**Context:** Project requirement to break work into small, reviewable
stages.
**Decision:** Work proceeds through Stages 0–8 as defined in
`PROJECT_PLAN.md`. No stage's code is written before the prior stage is
approved, and no stage writes deliverables that belong to a later stage.

### D-004 — Historical range: 2013-06-01 through 2026-05-31 (confirmed)
**Status:** Confirmed
**Context:** Originally proposed as "program launch (2013) through the
most recently available month," pending confirmation against actual data
availability.
**Decision:** Confirmed by direct investigation of
`nyu-datasets.citibike.m_daily_trips` (see D-010): the table's date range
is 2013-06-01 through 2026-05-31 inclusive. This supersedes the earlier
approximate interpretation.
**Alternatives considered:** A fixed trailing 13-year window ending at
project start date — not applicable now that the actual source table's
range is known directly.

### D-005 — Weather table confirmed: identity, schema grain, and date range
**Status:** Confirmed
**Context:** Originally the weather table's existence, schema, and
location were all unknown; later its identity was confirmed but its grain
was not.
**Decision:** The table is confirmed as
`nyu-datasets.weather.m_weather_daily_nyc`, containing 54,912 daily
records, one record per date, no duplicate dates, spanning 1876-01-01
through 2026-05-29. See `DATA_DICTIONARY.md` Section 4 for full detail.
Exact column names/types and derived rain/snow thresholds remain
undocumented pending further investigation.

### D-006 — Google BigQuery as the target warehouse
**Status:** Accepted
**Context:** Explicit project requirement ("loads the data into
BigQuery").
**Decision:** BigQuery is the warehouse for all standardized trip data,
daily summaries, and the weather join. No alternative warehouse is being
evaluated.

### D-007 — Python for ETL, SQL for transformation models
**Status:** Proposed — needs confirmation
**Context:** Not explicitly specified by the owner. Python + SQL is the
common pattern for BigQuery-based pipelines and matches the folder
structure already proposed (`src/` for Python, `sql/models/` for SQL).
**Decision (proposed):** Use Python for extraction/loading scripts and SQL
for all transformation models. To be confirmed before Stage 2 begins.

### D-008 — No ETL or dashboard code in Stage 0
**Status:** Accepted
**Context:** Explicit instruction for this task.
**Decision:** Stage 0 delivers only documentation, folder structure, and
placeholder/config files. No extraction, transformation, loading, SQL
model, or dashboard code is included.

### D-009 — Use provided BigQuery datasets instead of downloading public Citi Bike files
**Status:** Accepted
**Context:** The instructor confirmed the project must use provided
BigQuery datasets rather than extracting public Citi Bike trip files from
S3/HTTP.
**Decision:** The two confirmed source tables are:
- `nyu-datasets.citibike.m_daily_trips`
- `nyu-datasets.weather.m_weather_daily_nyc`

Extraction (Stage 2) is redefined as reading from these provided tables
rather than downloading and parsing external files. The public-file,
trip-level schema-era assumptions previously recorded in
`DATA_DICTIONARY.md` Section 1 are retained for historical reference only
and no longer describe the project's actual data source (see D-010).
**Note:** This may reduce or change the scope of Stages 2–5 in
`PROJECT_PLAN.md` (e.g., less file-download logic, possibly simpler
transformation given the source is already daily-grain — see D-010). That
plan revision is out of scope for this update and is not made here.

### D-010 — `nyu-datasets.citibike.m_daily_trips` confirmed to be a daily-grain table (Stage 1 investigation)
**Status:** Confirmed
**Context:** Direct investigation of `nyu-datasets.citibike.m_daily_trips`.
**Decision:** Record the following as verified facts, not assumptions:
- The table contains 4,738 rows.
- Its date range is 2013-06-01 through 2026-05-31.
- Exactly one row exists per distinct date (no duplicate dates found).
- Geography-based totals reconcile exactly.

This confirms the table is pre-aggregated at daily grain rather than
containing raw, trip-level rows, contradicting the original assumption in
`DATA_DICTIONARY.md` Section 1 (kept for historical reference, now
superseded as the description of the actual source — see D-009).

### D-011 — 10 missing calendar dates confirmed in `nyu-datasets.citibike.m_daily_trips`
**Status:** Confirmed
**Context:** D-010 established that the table has 4,738 rows across a
2013-06-01–2026-05-31 range spanning 4,748 calendar days, implying a
10-date gap. Direct investigation confirmed the 10 specific missing
dates:
- 2016-01-23
- 2016-01-24
- 2016-01-25
- 2016-01-26
- 2017-02-09
- 2017-03-14
- 2017-03-15
- 2017-03-16
- 2021-02-02
- 2026-02-23
**Decision:** Record these 10 dates as confirmed missing from the table.
No cause is speculated (e.g., source outage, upstream exclusion, system
gap) — see D-013 for how these are handled downstream.

### D-012 — Rider-type total reconciliation anomalies on 251 days, 2016–2017
**Status:** Accepted as a documented observation — cause unresolved
**Context:** Investigation found rider-type totals do not reconcile
exactly on 251 specific days, concentrated in 2016–2017 (previously
bounded to 2016-03-23 through 2017-03-31), even though geography totals
reconcile exactly across the full table (D-010). Most of the observed
differences appear small, but some larger differences were also observed.
The full distribution of difference sizes across all 251 days has not yet
been documented — do not characterize all 251 as uniformly small.
**Decision:** Document as a known, existing observation requiring no data
correction at this time. No cause is assumed or hypothesized (e.g.,
schema transition, rider-classification change) without supporting
official Citi Bike or NYU documentation. Revisit only if such
documentation surfaces, or if downstream analysis is materially affected.

### D-013 — Preserve missing calendar dates as missing; do not zero-fill or impute
**Status:** Accepted
**Context:** D-011 confirms 10 specific calendar dates are absent from
`nyu-datasets.citibike.m_daily_trips`. Two common alternative treatments
exist: (a) insert rows with zero-trip values for the missing dates, or (b)
impute estimated values (e.g., via interpolation).
**Decision:** Neither is done. The 10 missing dates are preserved as
missing (absent rows) in all downstream models and the final dashboard,
rather than being treated as confirmed zero-trip days or filled with
imputed values. A missing date is not evidence that zero rides occurred —
it may reflect a gap in the source table itself — so treating it as zero
or estimating a value would misrepresent the data. Any daily-completeness
data-quality check (see `DATA_DICTIONARY.md` Section 6) must treat these
10 dates as a known, accepted exception rather than a check failure,
unless future investigation changes this decision.
**Alternatives considered:** Zero-fill — rejected, since it assumes a
cause (zero ridership) not in evidence. Imputation/interpolation —
rejected, since it would fabricate ridership figures not present in the
source, which is unacceptable for a public dashboard used by
transportation planners.

### D-014 — Recommended join key: `date`
**Status:** Accepted
**Context:** Both source tables are confirmed daily-grain with one row
per calendar date: `nyu-datasets.citibike.m_daily_trips` (D-010) and
`nyu-datasets.weather.m_weather_daily_nyc` (D-005). Neither table's
Citi Bike side needs a station- or geography-level join key for the
dashboard's citywide daily metrics.
**Decision:** Join the two tables on `date` (exact calendar-date equality).
No secondary join key (e.g., geography) is required, since both tables
represent citywide daily aggregates.
**Alternatives considered:** None identified — a date-grain join is the
only join supported by both tables' confirmed structure.

### D-015 — Join validation: 2 of 4,738 Citi Bike days have no weather match
**Status:** Confirmed
**Context:** Joining `nyu-datasets.citibike.m_daily_trips`
(4,738 days, through 2026-05-31) to `nyu-datasets.weather.m_weather_daily_nyc`
(through 2026-05-29) on `date` (D-014) produces 4,736 successful matches
and 2 unmatched dates: 2026-05-30 and 2026-05-31.
**Decision:** Document this as an expected, explained gap, not a join
defect: the weather table's data currently ends 2026-05-29, two days
before the Citi Bike table's most recent date. These two trailing dates
will have no weather data until the weather source is refreshed with
later dates. No other cause is identified or needed — this is fully
explained by the two tables' differing as-of dates.

### D-016 — 24 missing calendar dates confirmed (by count) in the weather table; identities and cause unresolved
**Status:** Confirmed (count) — specific dates and cause not yet determined
**Context:** The weather table's confirmed range (1876-01-01 through
2026-05-29, inclusive) spans 54,936 inclusive calendar days (D-005). The
table has 54,912 unique dates, and no duplicate dates were found (D-005).
**Decision:** Because the row count and date-uniqueness are both
confirmed facts, the difference is an exact, verified count, not a guess:
54,936 − 54,912 = 24 calendar dates are missing from the table. This is
recorded as a confirmed fact. What remains unresolved is which 24 specific
dates are missing and why — unlike the Citi Bike table's missing dates
(D-011), where the exact dates were individually identified, the
weather table's missing dates have not yet been enumerated. Further
investigation is required to identify them before any cause is
considered.

### D-017 — Stage 3 scope: one-month (January 2025) prototype, explicit destination controls
**Status:** Accepted
**Context:** Stage 3 is the first stage that writes anything, so the
write path needs firm guardrails before any code is implemented.
**Decision:** Stage 3 implements a single end-to-end prototype scoped to
one calendar month (January 2025) only — not the full historical range.
The load target is controlled entirely by caller-supplied configuration:
`BQ_DESTINATION_PROJECT_ID` (falls back to `GCP_PROJECT_ID` if unset) and
`BQ_DESTINATION_DATASET` (required, no default). The destination dataset
is never auto-created — if it does not already exist, the load fails with
BigQuery's own "not found" error rather than this code creating one. The
destination table name is derived (`citibike_weather_prototype_2025_01`),
not accepted as a free-form argument, so a caller cannot point the load at
an arbitrary table. The load uses `CREATE OR REPLACE TABLE ... AS SELECT`
(CTAS), so re-running the prototype is idempotent — it fully replaces the
table's contents in one atomic statement rather than appending duplicate
rows.
**Alternatives considered:** Defaulting the destination to the same
project as the source tables — rejected, since the source project
(`nyu-datasets`) is a shared teaching project, not somewhere this project
should ever write.

### D-018 — Full 15-column Citi Bike shape and curated 8-field weather selection retained; no wildcard select
**Status:** Accepted
**Context:** An earlier draft considered `c.* EXCEPT(date)` / `w.*` for
brevity.
**Decision:** The prototype query explicitly lists all 15 confirmed
Citi Bike columns (`DATA_DICTIONARY.md` Section 1a) and the 8 curated
weather fields (`tmin_f`, `tmax_f`, `tavg_f`, `prcp_inches`, `is_rainy`,
`snow_inches`, `is_snowy`, `season`) by name — no `SELECT *` or `EXCEPT`
wildcard anywhere in `src/transformation/prototype_query.py`. This makes
the destination schema self-documenting from the query text and prevents
an unreviewed upstream schema change from silently changing the
destination table's shape.

### D-019 — V1-V11 validation rule set; V8/V9 reclassified as source-quality findings, not failures
**Status:** Accepted
**Context:** The Stage 3 prototype needs both structural validation
(row counts, date completeness, join integrity) and reconciliation
checks carried over from Stage 1 (rider-type and geography totals,
D-012).
**Decision:** `src/transformation/prototype_validator.py` implements 11
rules:
- V1 destination row count == Citi Bike source row count (for the month)
- V2 no duplicate dates (row count == distinct dates)
- V3 no null dates
- V4 destination date range falls within the requested month
- V5 additive Citi Bike columns: `SUM(destination) == SUM(source)`
- V6 non-additive Citi Bike columns (avg/median/distance): per-date,
  null-safe, tolerance-based comparison
- V7 `weather_matched` is never null; matched + unmatched == total rows
- V8 rider-type reconciliation (member + casual == total)
- V9 geography reconciliation (nyc + jc == total)
- V10 non-additive weather columns, compared only for matched dates,
  null-safe and tolerance-based
- V11 domain check: non-null source `is_rainy`/`is_snowy` values must be
  in `{0, 1}` before being cast to `BOOL`

V8 and V9 are deliberately kept out of `mismatches` and reported instead
as `source_quality_findings` (affected dates and exact differences). This
is because the underlying discrepancy (D-012) pre-exists in the source
table — it is not something this transformation introduces — so it must
never flip the prototype's overall `passed` result to `False`, and the
source values are never altered to force reconciliation.
**Alternatives considered:** Treating V8/V9 as hard failures like the
other rules — rejected, since that would misrepresent a known,
pre-existing source condition as a bug in this project's transformation
logic.

### D-020 — Null-safe, tolerance-based comparisons; V10's Boolean comparison basis is `CAST(source AS BOOL)`
**Status:** Accepted
**Context:** Weather fields are nullable, and Citi Bike/weather float
columns should not be compared with exact equality.
**Decision:** All FLOAT64 comparisons (V6, V10's numeric fields) use a
null-safe, tolerance-based check: both-null counts as equal, exactly one
null counts as a mismatch, otherwise compare within a fixed tolerance
(1e-6) rather than exact equality. Exact-value comparisons (season,
weather-matched flag) rely on plain equality, which is already null-safe
in Python (`None == None` is `True`). V10's Boolean indicator comparison
is explicitly defined as comparing the destination's stored `is_rainy` /
`is_snowy` (BOOL) against `CAST(source.is_rainy AS BOOL)` /
`CAST(source.is_snowy AS BOOL)` — implemented via a small, pure,
unit-tested helper (`cast_int_indicator_to_bool`) that mirrors BigQuery's
own `CAST(... AS BOOL)` semantics, rather than assuming the destination
and source values already agree.

### D-021 — Query parameters for the date range; matched/unmatched/match-rate reporting added
**Status:** Accepted
**Context:** Embedding date literals directly in SQL text is both a
minor injection-surface concern and makes the query harder to reuse for
a different month later.
**Decision:** `@start_date` and `@end_date` are bound as real BigQuery
query parameters (`bigquery.ScalarQueryParameter`) everywhere the
prototype month is used — the load query, the Citi Bike source scoping
query, and the weather source scoping query. No date literal is ever
interpolated into SQL text. The validation report additionally surfaces
`matched_weather_rows`, `unmatched_weather_rows`, and
`weather_match_rate` (matched / total destination rows), extending the
join-coverage reporting pattern already established for Stage 1 (D-015).
