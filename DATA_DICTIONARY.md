# Data Dictionary

**Status: partially confirmed.** Sections 1a, 4, and 5 below record
verified facts from direct investigation of the two provided BigQuery
source tables (Stage 1 investigation). Everything else is still either
general public knowledge, an explicit assumption, or marked TBD, clearly
labeled. Every remaining unconfirmed entry must be verified during further
investigation and updated in place.

---

## 1. Citi Bike data — source and grain

### 1a. Confirmed facts — `nyu-datasets.citibike.m_daily_trips` (Stage 1 investigation)

**Status: confirmed**, except where noted.

| Fact | Value | Status |
|---|---|---|
| Grain | One row per calendar date (pre-aggregated daily table, **not** trip-level) | Confirmed |
| Row count | 4,738 | Confirmed |
| Date range | 2013-06-01 through 2026-05-31 (inclusive) | Confirmed |
| Uniqueness | Exactly one row per distinct date; no duplicate dates found | Confirmed |
| Geography totals | Reconcile exactly | Confirmed |
| Rider-type totals | 251 days show reconciliation anomalies, concentrated in 2016–2017; most observed differences appear small but some larger differences were also observed — full distribution not yet documented | Confirmed observation; cause not speculated (see `DECISIONS.md` D-012) |
| Date coverage | 10 calendar dates confirmed missing from the table (see list below) | Confirmed (see `DECISIONS.md` D-011) |
| Column names, data types, primary-key candidates | Not yet available | TBD — pending BigQuery schema access (`INFORMATION_SCHEMA.COLUMNS`) |

**Confirmed missing dates (10 total), cause not speculated:**
2016-01-23, 2016-01-24, 2016-01-25, 2016-01-26, 2017-02-09, 2017-03-14,
2017-03-15, 2017-03-16, 2021-02-02, 2026-02-23. These dates are preserved
as missing — not zero-filled, not imputed — in all downstream models and
the dashboard (see `DECISIONS.md` D-013).

See `DECISIONS.md` D-009 through D-013 for full context and rationale.

### 1b. Superseded assumption — public trip-level CSV files (historical reference only)

**This section no longer describes the project's actual data source.**
The project now reads directly from the provided
`nyu-datasets.citibike.m_daily_trips` table (see 1a and `DECISIONS.md`
D-009), which is confirmed to be daily-grain, not trip-level. The tables
below are kept only as a record of the original assumption, made before
the provided-dataset pivot, and should not be used to plan Stage 3
transformation logic.

Public knowledge suggested Citi Bike's published trip-data *files* (the
public S3/HTTP distribution, no longer the project's source) used at
least two distinct schemas:

#### Era A (assumed ~2013 – early 2021)

| Column | Type (assumed) | Notes |
|---|---|---|
| `tripduration` | integer (seconds) | |
| `starttime` | timestamp | |
| `stoptime` | timestamp | |
| `start station id` | integer | |
| `start station name` | string | |
| `start station latitude` | float | |
| `start station longitude` | float | |
| `end station id` | integer | |
| `end station name` | string | |
| `end station latitude` | float | |
| `end station longitude` | float | |
| `bikeid` | integer | |
| `usertype` | string | `Subscriber` / `Customer` |
| `birth year` | integer | often sparse/missing |
| `gender` | integer | coded; often sparse/missing |

#### Era B (assumed ~2021 – present, post Lyft operational change)

| Column | Type (assumed) | Notes |
|---|---|---|
| `ride_id` | string | |
| `rideable_type` | string | e.g. `classic_bike`, `electric_bike` |
| `started_at` | timestamp | replaces `starttime` |
| `ended_at` | timestamp | replaces `stoptime` |
| `start_station_name` | string | |
| `start_station_id` | string | |
| `end_station_name` | string | |
| `end_station_id` | string | |
| `start_lat` | float | |
| `start_lng` | float | |
| `end_lat` | float | |
| `end_lng` | float | |
| `member_casual` | string | `member` / `casual` — replaces `usertype` |

---

## 2. Planned canonical trip-level schema (Stage 3 output — TBD, scope may change)

Originally planned to be finalized in Stage 3 by reconciling the trip-level
schema variants above. Since `nyu-datasets.citibike.m_daily_trips` is
confirmed to be daily-grain (Section 1a), a trip-level canonical schema
may not be necessary at all — Stage 3's scope should be revisited once
column-level detail for the provided table is available. Not resolved in
this update (see `DECISIONS.md` D-009).

## 3. Planned daily summary schema (Stage 5 output — TBD)

Expected grain: one row per calendar date. Expected to include the metrics
listed in `README.md` (total rides, average trip duration, rides by user
type, rides by weekday, plus fields needed to support temperature-range
and rain/snow breakdowns after the weather join in Stage 6). Given
`nyu-datasets.citibike.m_daily_trips` already appears to be daily-grain
(Section 1a), this stage may turn out to be much closer to
"select/reshape" than "aggregate from trip-level" — to be confirmed once
its column list is known.

## 4. Provided daily weather table — `nyu-datasets.weather.m_weather_daily_nyc` (confirmed grain)

**Status: confirmed**, except where noted.

| Fact | Value | Status |
|---|---|---|
| Grain | One record per date | Confirmed |
| Row count | 54,912 | Confirmed |
| Date range | 1876-01-01 through 2026-05-29 (inclusive) | Confirmed |
| Uniqueness | No duplicate dates | Confirmed |
| Date coverage | 24 calendar dates confirmed missing (54,936 calendar days in range vs. 54,912 unique dates, no duplicates) | Count confirmed; specific dates and cause unresolved (see `DECISIONS.md` D-016) |
| Column names, data types (e.g., temperature, precipitation, snow fields), rain/snow thresholds | Not yet available | TBD — pending further investigation |

## 5. Join validation — Citi Bike ↔ Weather

**Recommended and used join key: `date`.** Both tables are confirmed
daily-grain with one row per calendar date (Sections 1a and 4), so a
direct date-equality join is the natural and only supported key (see
`DECISIONS.md` D-014). No geography-level join key is needed — both
tables are citywide daily aggregates.

**Validation result (confirmed):**

| Fact | Value |
|---|---|
| Citi Bike days | 4,738 |
| Successful weather matches | 4,736 |
| Unmatched dates | 2026-05-30, 2026-05-31 |

**Explanation (factual, not speculative):** these 2 dates are unmatched
because the weather table's data currently ends 2026-05-29 — two days
before the Citi Bike table's most recent date (2026-05-31). This is fully
explained by the two tables' differing as-of dates, not a join defect
(see `DECISIONS.md` D-015). Any daily summary + weather join will have
exactly these 2 trailing dates without weather data until the weather
source is refreshed.

## 5a. Stage 3 prototype — destination schema (January 2025 only)

**Status: implemented (Stage 3), scoped to one month.** Table:
`{destination_project}.{destination_dataset}.citibike_weather_prototype_2025_01`
(destination project/dataset are caller-supplied — see
`config/.env.example`; never hardcoded, never auto-created).

| Column | Source | Notes |
|---|---|---|
| `date` … `avg_distance_meters` (15 columns) | `nyu-datasets.citibike.m_daily_trips` | Full confirmed shape from Section 1a, selected explicitly (no `c.*`) |
| `weekday` | Derived | `FORMAT_DATE('%A', date)` |
| `tmin_f`, `tmax_f`, `tavg_f`, `prcp_inches`, `snow_inches`, `season` | `nyu-datasets.weather.m_weather_daily_nyc` | Curated subset, selected explicitly (no `w.*`) |
| `is_rainy`, `is_snowy` | `nyu-datasets.weather.m_weather_daily_nyc` | Source INT64 0/1 indicators, `CAST(... AS BOOL)` at selection time |
| `weather_matched` | Derived | `(weather.date IS NOT NULL)` — `TRUE` when the Citi Bike date has a weather match |

Validation rules (V1–V11) implemented in
`src/transformation/prototype_validator.py`; see `DECISIONS.md` D-017
through D-021 for the full rationale, including why V8/V9 are reported as
source-quality findings rather than validation failures.

## 5b. Stage 4 monthly pipeline — destination schema (any valid month)

**Status: implemented (Stage 4), generalized from 5a.** Table:
`{destination_project}.{destination_dataset}.citibike_weather_monthly_{YYYY}_{MM}`
— note the `_monthly_` prefix, distinct from Stage 3's `_prototype_`
naming (5a); the two coexist rather than one overwriting the other (see
`DECISIONS.md` D-022). Column shape is byte-for-byte identical to 5a —
same 15 Citi Bike columns, same derived `weekday`, same 8 curated
weather fields, same `is_rainy`/`is_snowy` `CAST(... AS BOOL)`, same
`weather_matched` flag — since `src/transformation/prototype_query.py`
was reused unchanged (see `DECISIONS.md` D-022).

**Availability:** a requested month is only valid if fully contained in
the LIVE effective shared range — `max(citibike_min_date,
weather_min_date)` through `min(citibike_max_date, weather_max_date)`,
recomputed on every run (never a hardcoded constant, never derived from
the current wall-clock date). A month only partially covered by the
shared range is rejected, not truncated (`DECISIONS.md` D-023).

Same V1–V11 validation rules as 5a (unchanged), plus matched/unmatched/
match-rate reporting. Exit codes and `--dry-run`/`--validate-only`
behavior: see `DECISIONS.md` D-024 and
`src/pipeline/monthly_pipeline.py`.

## 5c. Stage 6 analytics table — dashboard-ready daily grain

**Status: implemented (Stage 6).** Table:
`{destination_project}.{destination_dataset}.citibike_weather_analytics`
— a single, fixed name (not month-suffixed, not user-supplied), so
re-runs overwrite it via `CREATE OR REPLACE TABLE` (see `DECISIONS.md`
D-030). Deliberately **not** prefixed `citibike_weather_monthly_`, so it
can never be swept back into monthly-table discovery.

Built by combining the existing Stage 4/5 monthly destination tables
(`citibike_weather_monthly_YYYY_MM`, §5b) with a plain `UNION ALL` —
never the raw public sources, never a wildcard. The monthly tables are
non-overlapping by construction, so the union is naturally one row per
`date`; there is **no** silent de-duplication (a duplicate date would
indicate an upstream bug and fails validation rule A1). Columns carried
from the monthly output are byte-for-byte unchanged; only the three
derived fields are added.

| Column | Type | Source |
|---|---|---|
| `date` | DATE | carried (grain key) |
| `num_trips` | INT64 | carried — total rides/day |
| `num_member_trips` | INT64 | carried |
| `num_casual_trips` | INT64 | carried |
| `avg_trip_duration_minutes` | FLOAT64 | carried |
| `weekday` | STRING | carried (day name; from the Stage 3/4 `FORMAT_DATE('%A', date)`) |
| `season` | STRING | carried |
| `tmin_f` / `tmax_f` / `tavg_f` | FLOAT64 | carried |
| `prcp_inches` / `snow_inches` | FLOAT64 | carried |
| `is_rainy` / `is_snowy` | BOOL | carried |
| `weather_matched` | BOOL | carried |
| `temperature_band` | STRING | **derived** from `tavg_f` |
| `rain_category` | STRING | **derived** from `is_rainy` |
| `snow_category` | STRING | **derived** from `is_snowy` |

The wider monthly column set (NYC/JC splits, classic/electric,
median duration, distance) is intentionally **not** carried, to keep the
analytics table minimal and focused on the seven dashboard metrics
(`DECISIONS.md` D-029). There is **no** provenance/`source_month` column
(owner decision).

### Derived-field definitions

**`temperature_band`** — from `tavg_f` (°F). Lower-inclusive /
upper-exclusive bands; a NULL `tavg_f` (unmatched-weather row) maps to
`Unknown`:

| Band | Condition on `tavg_f` |
|---|---|
| `Unknown` | IS NULL |
| `Freezing` | < 32 |
| `Cold` | 32 – < 50 |
| `Mild` | 50 – < 70 |
| `Warm` | 70 – < 85 |
| `Hot` | ≥ 85 |

**`rain_category`** — reuses the existing `is_rainy` BOOL indicator
(**not** re-thresholded from `prcp_inches`, so it can never diverge from
the monthly definition): `TRUE → 'Rainy'`, `FALSE → 'Dry'`,
`NULL → 'Unknown'`.

**`snow_category`** — reuses the existing `is_snowy` BOOL indicator:
`TRUE → 'Snowy'`, `FALSE → 'No Snow'`, `NULL → 'Unknown'`.

(The underlying `is_rainy` / `is_snowy` rain-vs-dry and snow-vs-no-snow
thresholds themselves are the Stage 3 curated-weather definitions in §4;
Stage 6 categorizes on those booleans rather than redefining them.)

### Validation (A1–A11, `src/analytics/analytics_validation.py`)

A1 no duplicate dates · A2 no null dates · A3 row count preserved vs. the
source union · A4 distinct-date count preserved · A5 ride counts
(`num_trips`/`num_member_trips`/`num_casual_trips`) preserved · A6 weather
measures (`prcp_inches`/`snow_inches`) preserved within float tolerance ·
A7 weather indicators (`COUNTIF` of `is_rainy`/`is_snowy`/
`weather_matched`) preserved · A8–A10 derived-field domain (each derived
column only takes its allowed values) · A11 a derived category is
`Unknown` **iff** its driving input is NULL. Preservation is
analytics-vs-source only; A5 does **not** assert
`num_member_trips + num_casual_trips == num_trips` (that rider-type
identity is a known source condition — §1a, D-012 — not enforced here).

## 6. Data-quality check reference

These checks (implemented in `tests/data_quality/` during Stage 7, but
considered from Stage 2 onward) apply to the fields above:

| Check | Applies to |
|---|---|
| Row counts (source vs. extracted vs. loaded) | All stages |
| Date completeness (no missing calendar days in summaries) | `nyu-datasets.citibike.m_daily_trips` — 10 known/accepted missing dates (see 1a, D-013) must not be flagged as failures; weather table — 24 confirmed missing dates, specific dates unresolved (see 4, D-016); daily summary |
| Duplicate detection (full-row and date level) | `nyu-datasets.citibike.m_daily_trips` (confirmed clean — see 1a), weather table (confirmed clean — see 4) |
| Missing-value checks on required fields | Citi Bike data, weather table |
| Invalid trip duration (<= 0 or implausibly large) | Only applicable if/when trip-level data is used; may not apply given 1a |
| Rider-type total reconciliation | `nyu-datasets.citibike.m_daily_trips` — known discrepancy on 251 days (see 1a, D-012) |
| Weather join coverage (% of days matched) | Confirmed at 4,736 / 4,738 (99.96%); 2 unmatched dates fully explained (see 5, D-015) |
