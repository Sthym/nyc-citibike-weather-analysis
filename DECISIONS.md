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
