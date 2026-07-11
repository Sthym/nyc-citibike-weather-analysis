# Data Dictionary

**Status: preliminary.** No source data has been investigated yet (that is
Stage 1). Everything below is either general public knowledge about the
Citi Bike dataset or an explicit assumption, clearly labeled. Every entry
here must be verified or corrected during Stage 1 and updated in place.

---

## 1. Citi Bike trip data — known schema eras (ASSUMPTION, to verify)

Public knowledge suggests Citi Bike's published trip-data files have used
at least two distinct schemas. Exact cutover dates and any additional
intermediate variants must be confirmed in Stage 1.

### Era A (assumed ~2013 – early 2021)

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

### Era B (assumed ~2021 – present, post Lyft operational change)

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

**Known differences to reconcile in Stage 3:** `tripduration` is not
present in Era B and must be derived as `ended_at - started_at`;
`bikeid`, `birth year`, and `gender` are not present in Era B; user-type
values change vocabulary (`Subscriber`/`Customer` vs. `member`/`casual`)
and must be standardized to one canonical set.

---

## 2. Planned canonical trip-level schema (Stage 3 output — TBD)

To be finalized in Stage 3 once Stage 1 confirms all schema variants.
Expected to include at minimum: a stable trip identifier, start/end
timestamps, derived trip duration, start/end station identifiers,
standardized rider type, and a source-schema-era flag for traceability.

## 3. Planned daily summary schema (Stage 5 output — TBD)

Expected grain: one row per calendar date. Expected to include the metrics
listed in `README.md` (total rides, average trip duration, rides by user
type, rides by weekday, plus fields needed to support temperature-range
and rain/snow breakdowns after the weather join in Stage 6).

## 4. Provided daily weather table (ASSUMPTION, to confirm — see DECISIONS.md D-005)

Location, grain, and exact columns are unknown until the owner identifies
the table or source. Commonly available fields in NYC daily weather
datasets (e.g., NOAA GHCN-Daily) that this project would need are assumed
to include: date, maximum temperature, minimum temperature, precipitation
amount, snowfall amount, and snow depth. Rain/dry and snow/non-snow
thresholds derived from these fields must be explicitly defined and
recorded here once confirmed (see `PROJECT_PLAN.md` Stage 6).

## 5. Data-quality check reference

These checks (implemented in `tests/data_quality/` during Stage 7, but
considered from Stage 2 onward) apply to the fields above:

| Check | Applies to |
|---|---|
| Row counts (source vs. extracted vs. loaded) | All stages |
| Date completeness (no missing calendar days in summaries) | Daily summary, weather join |
| Duplicate detection (full-row and trip-id level) | Trip data |
| Missing-value checks on required fields | Trip data, weather table |
| Invalid trip duration (<= 0 or implausibly large) | Trip data |
| Weather join coverage (% of days matched) | Weather join |
