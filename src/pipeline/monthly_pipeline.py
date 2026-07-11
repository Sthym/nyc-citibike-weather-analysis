"""Stage 4 orchestration: the reusable monthly ETL pipeline.

This module performs I/O (BigQuery reads/writes), but every dependency
(the read-only client, the raw query client, the loader) is injected as
a parameter, so ``execute()`` is fully unit-testable against fakes with
zero network access -- the same pattern used throughout this project
(``BigQueryReadOnlyClient``, ``PrototypeLoader``).

Reuses, UNCHANGED, from Stage 3:
  - ``src.transformation.prototype_query.build_prototype_query`` /
    ``month_range`` -- the join SQL is already month-agnostic
  - ``src.transformation.prototype_validator.validate_prototype`` and
    ``ObservedPrototypeData`` -- V1-V11 logic is already month-agnostic
  - ``src.extraction.table_id.validate_table_id``
  - ``src.extraction.bigquery_client.BigQueryReadOnlyClient`` --
    ``get_date_range_stats`` is repurposed here for live month
    availability checks
  - ``src.loading.prototype_loader.PrototypeLoader`` -- only gained one
    small additive ``table_name`` override parameter

Only the destination table naming, month/date validation, dry-run, and
validate-only orchestration are new in Stage 4.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from google.cloud import bigquery

from src.extraction.table_id import validate_table_id
from src.pipeline.month_period import (
    InvalidMonthPeriodError,
    compute_effective_range,
    parse_month_period,
)
from src.transformation.prototype_query import build_prototype_query
from src.transformation.prototype_validator import (
    ADDITIVE_CITIBIKE_COLUMNS,
    ObservedPrototypeData,
    cast_int_indicator_to_bool,
    validate_prototype,
)

# --- Exit codes -------------------------------------------------------
EXIT_SUCCESS = 0
EXIT_UNEXPECTED_ERROR = 1
EXIT_USAGE_ERROR = 2
EXIT_CONFIG_ERROR = 3
EXIT_INVALID_MONTH = 4
EXIT_AUTH_OR_QUERY_ERROR = 5
EXIT_LOAD_ERROR = 6
EXIT_VALIDATION_FAILURE = 7

# --- Shared SQL templates (moved from the Stage 3 script, unchanged) --
STRUCTURAL_SQL_TEMPLATE = """\
SELECT
  COUNT(*) AS row_count,
  COUNT(DISTINCT date) AS distinct_dates,
  COUNTIF(date IS NULL) AS null_dates,
  MIN(date) AS min_date,
  MAX(date) AS max_date,
  COUNTIF(weather_matched) AS matched,
  COUNTIF(NOT weather_matched) AS unmatched,
  COUNTIF(weather_matched IS NULL) AS null_flag
FROM `{table}`
"""

DESTINATION_ROWS_SQL_TEMPLATE = """\
SELECT
  date, avg_trip_duration_minutes, median_trip_duration_minutes,
  avg_distance_meters, weather_matched, tmin_f, tmax_f, tavg_f,
  prcp_inches, is_rainy, snow_inches, is_snowy, season
FROM `{table}`
"""

CITIBIKE_ROWS_SQL_TEMPLATE = """\
SELECT
  date, avg_trip_duration_minutes, median_trip_duration_minutes,
  avg_distance_meters, num_member_trips, num_casual_trips,
  num_nyc_trips, num_jc_trips, num_trips
FROM `{table}`
WHERE date BETWEEN @start_date AND @end_date
"""

WEATHER_ROWS_SQL_TEMPLATE = """\
SELECT
  date, tmin_f, tmax_f, tavg_f, prcp_inches, snow_inches,
  is_rainy, is_snowy, season
FROM `{table}`
WHERE date BETWEEN @start_date AND @end_date
"""


def _additive_sum_sql(table: str, where_clause: str = "") -> str:
    select_list = ",\n  ".join(f"SUM({c}) AS {c}" for c in ADDITIVE_CITIBIKE_COLUMNS)
    sql = f"SELECT\n  {select_list}\nFROM `{table}`"
    if where_clause:
        sql += f"\n{where_clause}"
    return sql


def _run_query(
    query_client: bigquery.Client,
    sql: str,
    location: str,
    start_date=None,
    end_date=None,
) -> List[Any]:
    job_config = None
    if start_date is not None and end_date is not None:
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("start_date", "DATE", start_date),
                bigquery.ScalarQueryParameter("end_date", "DATE", end_date),
            ]
        )
    query_job = query_client.query(sql, job_config=job_config, location=location)
    return list(query_job.result())


def qualified_table_id(table_id: str) -> str:
    ref = validate_table_id(table_id)
    return f"{ref.project}.{ref.dataset_id}.{ref.table_id}"


def gather_observed_data(
    query_client: bigquery.Client,
    location: str,
    qualified_destination: str,
    qualified_citibike: str,
    qualified_weather: str,
    start_date,
    end_date,
) -> ObservedPrototypeData:
    """Re-read destination + both sources (scoped to the month) and
    assemble the ``ObservedPrototypeData`` the V1-V11 rules need.

    Shared by both the full-run path and ``--validate-only`` -- neither
    duplicates this query logic.
    """
    structural = _run_query(
        query_client, STRUCTURAL_SQL_TEMPLATE.format(table=qualified_destination), location
    )[0]

    destination_additive_sums: Dict[str, float] = dict(
        _run_query(query_client, _additive_sum_sql(qualified_destination), location)[0].items()
    )
    source_additive_sums: Dict[str, float] = dict(
        _run_query(
            query_client,
            _additive_sum_sql(
                qualified_citibike, where_clause="WHERE date BETWEEN @start_date AND @end_date"
            ),
            location,
            start_date,
            end_date,
        )[0].items()
    )

    citibike_source_row_count = _run_query(
        query_client,
        f"SELECT COUNT(*) AS row_count FROM `{qualified_citibike}` "
        "WHERE date BETWEEN @start_date AND @end_date",
        location,
        start_date,
        end_date,
    )[0]["row_count"]

    destination_rows_by_date: Dict[Any, Dict[str, Any]] = {}
    for row in _run_query(
        query_client, DESTINATION_ROWS_SQL_TEMPLATE.format(table=qualified_destination), location
    ):
        row_dict = dict(row.items())
        destination_rows_by_date[row_dict["date"]] = row_dict

    citibike_source_rows_by_date: Dict[Any, Dict[str, Any]] = {}
    citibike_reconciliation_rows: List[Dict[str, Any]] = []
    for row in _run_query(
        query_client,
        CITIBIKE_ROWS_SQL_TEMPLATE.format(table=qualified_citibike),
        location,
        start_date,
        end_date,
    ):
        row_dict = dict(row.items())
        citibike_source_rows_by_date[row_dict["date"]] = row_dict
        citibike_reconciliation_rows.append(row_dict)

    weather_source_rows_by_date: Dict[Any, Dict[str, Any]] = {}
    weather_indicator_rows: List[Dict[str, Any]] = []
    for row in _run_query(
        query_client,
        WEATHER_ROWS_SQL_TEMPLATE.format(table=qualified_weather),
        location,
        start_date,
        end_date,
    ):
        row_dict = dict(row.items())
        weather_indicator_rows.append(dict(row_dict))
        cast_row = dict(row_dict)
        cast_row["is_rainy"] = cast_int_indicator_to_bool(row_dict["is_rainy"])
        cast_row["is_snowy"] = cast_int_indicator_to_bool(row_dict["is_snowy"])
        weather_source_rows_by_date[row_dict["date"]] = cast_row

    return ObservedPrototypeData(
        destination_row_count=structural["row_count"],
        distinct_date_count=structural["distinct_dates"],
        null_date_count=structural["null_dates"],
        min_date=structural["min_date"],
        max_date=structural["max_date"],
        matched_weather_rows=structural["matched"],
        unmatched_weather_rows=structural["unmatched"],
        weather_matched_null_count=structural["null_flag"],
        citibike_source_row_count=citibike_source_row_count,
        destination_additive_sums=destination_additive_sums,
        source_additive_sums=source_additive_sums,
        destination_rows_by_date=destination_rows_by_date,
        citibike_source_rows_by_date=citibike_source_rows_by_date,
        weather_source_rows_by_date=weather_source_rows_by_date,
        citibike_reconciliation_rows=citibike_reconciliation_rows,
        weather_indicator_rows=weather_indicator_rows,
    )


def estimate_bytes_processed(
    query_client: bigquery.Client,
    select_sql: str,
    location: str,
    start_date,
    end_date,
) -> int:
    """Real (zero-cost, zero-write) BigQuery dry-run to estimate bytes
    processed. Requires a live, authenticated BigQuery call -- if it
    fails, the caller must treat that as an error (exit 5), never
    report "unavailable" as if the dry run had succeeded.
    """
    job_config = bigquery.QueryJobConfig(
        dry_run=True,
        use_query_cache=False,
        query_parameters=[
            bigquery.ScalarQueryParameter("start_date", "DATE", start_date),
            bigquery.ScalarQueryParameter("end_date", "DATE", end_date),
        ],
    )
    query_job = query_client.query(select_sql, job_config=job_config, location=location)
    return query_job.total_bytes_processed


def execute(
    *,
    year: int,
    month: int,
    table_name: str,
    dry_run: bool,
    validate_only: bool,
    config,
    destination_project: str,
    destination_dataset: str,
    read_client,
    query_client,
    loader,
    print_fn=print,
) -> int:
    """Run one full Stage 4 pipeline invocation and return an exit code.

    Order of operations (see DECISIONS.md D-02x for the rationale
    behind each exit code):
      1. Validate the destination table id shape (config-level) -> 3
      2. Fetch LIVE source date ranges for both tables -> 5 on failure
      3. Validate the requested month against the live effective shared
         range (full containment only; partial months rejected) -> 4
      4. --dry-run: build SQL, run a live BigQuery dry-run for a bytes
         estimate -> 5 on failure, otherwise 0 (never writes)
      5. Full run (not dry-run, not validate-only): CREATE OR REPLACE
         TABLE -> 6 on failure
      6. Re-read destination + sources and validate (V1-V11) -> 7 if
         validation fails, otherwise 0
    (validate-only skips step 5 entirely; dry-run returns before ever
    reaching step 5/6.)
    """
    destination_table_id = f"{destination_project}.{destination_dataset}.{table_name}"
    try:
        validate_table_id(destination_table_id)
    except ValueError as exc:
        print_fn(f"[CONFIG ERROR] {exc}")
        return EXIT_CONFIG_ERROR

    try:
        citibike_stats = read_client.get_date_range_stats(config.citibike_table)
        weather_stats = read_client.get_date_range_stats(config.weather_table)
    except Exception as exc:  # noqa: BLE001 -- any live-call failure is exit 5
        print_fn(f"[AUTH/QUERY ERROR] failed to retrieve live source date ranges: {exc}")
        return EXIT_AUTH_OR_QUERY_ERROR

    effective_min_date, effective_max_date = compute_effective_range(
        citibike_stats["min_date"],
        citibike_stats["max_date"],
        weather_stats["min_date"],
        weather_stats["max_date"],
    )

    try:
        period = parse_month_period(year, month, effective_min_date, effective_max_date)
    except InvalidMonthPeriodError as exc:
        print_fn(f"[INVALID MONTH] {exc}")
        return EXIT_INVALID_MONTH

    qualified_citibike = qualified_table_id(config.citibike_table)
    qualified_weather = qualified_table_id(config.weather_table)
    qualified_destination = qualified_table_id(destination_table_id)
    select_sql = build_prototype_query(config.citibike_table, config.weather_table)

    if dry_run:
        try:
            bytes_estimate = estimate_bytes_processed(
                query_client, select_sql, config.bq_location, period.start_date, period.end_date
            )
        except Exception as exc:  # noqa: BLE001
            print_fn(f"[AUTH/QUERY ERROR] dry run failed: {exc}")
            return EXIT_AUTH_OR_QUERY_ERROR
        print_fn(f"[DRY RUN] destination: {qualified_destination}")
        print_fn(f"[DRY RUN] period: {period.start_date} .. {period.end_date}")
        print_fn(f"[DRY RUN] estimated bytes processed: {bytes_estimate}")
        return EXIT_SUCCESS

    if not validate_only:
        try:
            loader.load(
                destination_project=destination_project,
                destination_dataset=destination_dataset,
                year=year,
                month=month,
                citibike_table=config.citibike_table,
                weather_table=config.weather_table,
                start_date=period.start_date,
                end_date=period.end_date,
                table_name=table_name,
            )
        except Exception as exc:  # noqa: BLE001
            print_fn(f"[LOAD ERROR] {exc}")
            return EXIT_LOAD_ERROR
        print_fn(f"Loaded: {qualified_destination}")

    try:
        observed = gather_observed_data(
            query_client,
            config.bq_location,
            qualified_destination,
            qualified_citibike,
            qualified_weather,
            period.start_date,
            period.end_date,
        )
    except Exception as exc:  # noqa: BLE001
        print_fn(f"[AUTH/QUERY ERROR] failed to gather observed data: {exc}")
        return EXIT_AUTH_OR_QUERY_ERROR

    result = validate_prototype(observed, period.start_date, period.end_date)

    print_fn(f"[{'PASS' if result.passed else 'FAIL'}] {qualified_destination}")
    print_fn(f"  matched_weather_rows:   {result.matched_weather_rows}")
    print_fn(f"  unmatched_weather_rows: {result.unmatched_weather_rows}")
    if result.weather_match_rate is not None:
        print_fn(f"  weather_match_rate:     {result.weather_match_rate:.4f}")
    if result.mismatches:
        print_fn("  Mismatches:")
        for m in result.mismatches:
            print_fn(f"    - {m}")
    if result.source_quality_findings:
        print_fn("  Source-quality findings (reported, not failures; source values unchanged):")
        for finding in result.source_quality_findings:
            print_fn(f"    - {finding}")

    return EXIT_SUCCESS if result.passed else EXIT_VALIDATION_FAILURE
