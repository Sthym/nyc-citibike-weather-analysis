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
