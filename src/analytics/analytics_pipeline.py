"""Stage 6 orchestration: build the one dashboard-ready analytics table.

Like ``src.pipeline.monthly_pipeline.execute``, this module performs I/O
(BigQuery list/read/write) but every dependency (the discovery client,
the query client, the loader) is injected, so ``execute()`` is fully
unit-testable against fakes with zero network access.

Reuses, UNCHANGED:
  - ``src.extraction.table_id.validate_table_id``
  - ``src.pipeline.monthly_pipeline``'s exit-code constants (0-3, 5, 6,
    7) and its ``qualified_table_id`` helper -- imported, never
    redefined. Exit code 4 (invalid/unavailable input) is reused, via
    the ``EXIT_NO_SOURCE_TABLES`` alias, for the "no monthly tables to
    combine" precondition (same aliasing precedent as Stage 5's
    ``EXIT_INVALID_RANGE``; see ``DECISIONS.md`` D-028). Exit code 8
    (logging failure) is Stage 5's and is NOT used or repurposed here --
    Stage 6 writes no run log.
  - ``src.analytics.analytics_query`` (SQL builder + derived-field value
    sets) and ``src.analytics.analytics_validation`` (pure A1-A11 rules).

New here: monthly-table discovery, the analytics CTAS orchestration, and
gathering the analytics-vs-source aggregates the validator compares.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from google.cloud import bigquery

from src.analytics.analytics_query import (
    RAIN_CATEGORY_VALUES,
    SNOW_CATEGORY_VALUES,
    TEMPERATURE_BAND_VALUES,
    analytics_table_name,
    build_analytics_select,
    build_union_select,
)
from src.analytics.analytics_validation import (
    ObservedAnalyticsData,
    validate_analytics,
)
from src.analytics.discovery import (
    NoMonthlyTablesError,
    discover_monthly_tables,
    missing_months_in_range,
    parse_monthly_table_name,
)
from src.extraction.table_id import validate_table_id
from src.pipeline.monthly_pipeline import (
    EXIT_AUTH_OR_QUERY_ERROR,
    EXIT_CONFIG_ERROR,
    EXIT_INVALID_MONTH,
    EXIT_LOAD_ERROR,
    EXIT_SUCCESS,
    EXIT_VALIDATION_FAILURE,
    qualified_table_id,
)

# Reuse Stage 4's exit code 4 for the "nothing available to process"
# precondition -- same numeric value, a clearer name at call sites.
EXIT_NO_SOURCE_TABLES = EXIT_INVALID_MONTH

YearMonth = Tuple[int, int]

# Aggregate template applied identically to the analytics table and to
# the UNION ALL of its source monthly tables, so preservation means
# "identical to the rows that went in". ``{relation}`` is either a
# backtick-quoted table id or a parenthesized union subquery.
AGGREGATE_SQL_TEMPLATE = """\
SELECT
  COUNT(*) AS row_count,
  COUNT(DISTINCT date) AS distinct_dates,
  COUNTIF(date IS NULL) AS null_dates,
  SUM(num_trips) AS num_trips,
  SUM(num_member_trips) AS num_member_trips,
  SUM(num_casual_trips) AS num_casual_trips,
  SUM(prcp_inches) AS prcp_inches,
  SUM(snow_inches) AS snow_inches,
  COUNTIF(is_rainy) AS count_rainy,
  COUNTIF(is_snowy) AS count_snowy,
  COUNTIF(weather_matched) AS count_weather_matched
FROM {relation}
"""

# Domain + Unknown/NULL-consistency checks, run only against the loaded
# analytics table (the derived columns exist only there). Allowed value
# sets are module constants (not user input) interpolated as string
# literals.
DOMAIN_SQL_TEMPLATE = """\
SELECT
  COUNTIF(temperature_band NOT IN ({temp_values})) AS bad_temperature_band,
  COUNTIF(rain_category NOT IN ({rain_values})) AS bad_rain_category,
  COUNTIF(snow_category NOT IN ({snow_values})) AS bad_snow_category,
  COUNTIF((tavg_f IS NULL) != (temperature_band = 'Unknown')) AS temp_consistency,
  COUNTIF((is_rainy IS NULL) != (rain_category = 'Unknown')) AS rain_consistency,
  COUNTIF((is_snowy IS NULL) != (snow_category = 'Unknown')) AS snow_consistency
FROM `{table}`
"""

_SUM_KEYS = ["num_trips", "num_member_trips", "num_casual_trips", "prcp_inches", "snow_inches"]
_INDICATOR_KEYS = ["count_rainy", "count_snowy", "count_weather_matched"]


def _value_list_sql(values: List[str]) -> str:
    """Render a list of string labels as a SQL literal ``IN`` list."""
    return ", ".join(f"'{v}'" for v in values)


def _run_query(query_client: bigquery.Client, sql: str, location: str) -> List[Any]:
    query_job = query_client.query(sql, location=location)
    return list(query_job.result())


def estimate_bytes_processed(query_client: bigquery.Client, select_sql: str, location: str) -> int:
    """Zero-cost, zero-write BigQuery dry-run for a bytes estimate. A
    failure here is a live-call failure the caller maps to exit 5 (never
    reported as if the estimate succeeded)."""
    job_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
    query_job = query_client.query(select_sql, job_config=job_config, location=location)
    return query_job.total_bytes_processed


def gather_observed_analytics(
    query_client: bigquery.Client,
    location: str,
    qualified_destination: str,
    monthly_table_ids: List[str],
) -> ObservedAnalyticsData:
    """Compute the analytics-table aggregates, the same aggregates over
    the source union, and the derived-field domain/consistency counts,
    and assemble the ``ObservedAnalyticsData`` the A1-A11 rules need.

    Shared by the full-run path and ``--validate-only`` -- neither
    duplicates this logic.
    """
    analytics_agg = _run_query(
        query_client, AGGREGATE_SQL_TEMPLATE.format(relation=f"`{qualified_destination}`"), location
    )[0]

    union_sql = build_union_select(monthly_table_ids)
    source_relation = "(\n" + union_sql + "\n)"
    source_agg = _run_query(
        query_client, AGGREGATE_SQL_TEMPLATE.format(relation=source_relation), location
    )[0]

    domain = _run_query(
        query_client,
        DOMAIN_SQL_TEMPLATE.format(
            table=qualified_destination,
            temp_values=_value_list_sql(TEMPERATURE_BAND_VALUES),
            rain_values=_value_list_sql(RAIN_CATEGORY_VALUES),
            snow_values=_value_list_sql(SNOW_CATEGORY_VALUES),
        ),
        location,
    )[0]

    return ObservedAnalyticsData(
        analytics_row_count=analytics_agg["row_count"],
        analytics_distinct_dates=analytics_agg["distinct_dates"],
        analytics_null_dates=analytics_agg["null_dates"],
        analytics_sums={key: analytics_agg[key] for key in _SUM_KEYS},
        analytics_indicator_counts={key: analytics_agg[key] for key in _INDICATOR_KEYS},
        source_row_count=source_agg["row_count"],
        source_distinct_dates=source_agg["distinct_dates"],
        source_sums={key: source_agg[key] for key in _SUM_KEYS},
        source_indicator_counts={key: source_agg[key] for key in _INDICATOR_KEYS},
        bad_temperature_band=domain["bad_temperature_band"],
        bad_rain_category=domain["bad_rain_category"],
        bad_snow_category=domain["bad_snow_category"],
        temperature_consistency_violations=domain["temp_consistency"],
        rain_consistency_violations=domain["rain_consistency"],
        snow_consistency_violations=domain["snow_consistency"],
    )


def _warn_missing_months(
    monthly_table_ids: List[str],
    start: Optional[YearMonth],
    end: Optional[YearMonth],
    print_fn,
) -> None:
    """When an explicit ``--start``/``--end`` window is requested, WARN
    (never fail) about months in the window that have no monthly table --
    the analytics table is still built from whatever is available."""
    if start is None or end is None:
        return
    present: List[YearMonth] = []
    for tid in monthly_table_ids:
        ym = parse_monthly_table_name(tid.rsplit(".", 1)[-1])
        if ym is not None:
            present.append(ym)
    for year, month in missing_months_in_range(present, start, end):
        print_fn(f"[WARN] requested month {year:04d}-{month:02d} has no monthly table; skipped")


def execute(
    *,
    table_name: Optional[str] = None,
    dry_run: bool,
    validate_only: bool,
    config,
    destination_project: str,
    destination_dataset: str,
    discovery_client,
    query_client,
    loader,
    start: Optional[YearMonth] = None,
    end: Optional[YearMonth] = None,
    print_fn=print,
) -> int:
    """Run one Stage 6 analytics build and return an exit code.

    Order of operations:
      1. Validate the destination table id shape -> 3.
      2. Discover the monthly destination tables to combine (optionally
         restricted to a [start, end] window) -> 5 on a live-listing
         failure, 4 if none are found.
      3. --dry-run: build SQL, run a live BigQuery dry-run for a bytes
         estimate -> 5 on failure, otherwise 0 (never writes).
      4. Full run (not dry-run, not validate-only): CREATE OR REPLACE
         TABLE via the loader -> 6 on failure.
      5. Re-read the analytics table + the source union and validate
         (A1-A11) -> 7 if validation fails, otherwise 0.
    (validate-only skips step 4; dry-run returns before step 4/5.)
    """
    resolved_table_name = table_name if table_name is not None else analytics_table_name()
    destination_table_id = f"{destination_project}.{destination_dataset}.{resolved_table_name}"
    try:
        validate_table_id(destination_table_id)
    except ValueError as exc:
        print_fn(f"[CONFIG ERROR] {exc}")
        return EXIT_CONFIG_ERROR

    try:
        monthly_table_ids = discover_monthly_tables(
            discovery_client, destination_project, destination_dataset, start=start, end=end
        )
    except NoMonthlyTablesError as exc:
        print_fn(f"[NO SOURCE TABLES] {exc}")
        return EXIT_NO_SOURCE_TABLES
    except Exception as exc:  # noqa: BLE001 -- any live listing failure is exit 5
        print_fn(f"[AUTH/QUERY ERROR] failed to list destination dataset: {exc}")
        return EXIT_AUTH_OR_QUERY_ERROR

    _warn_missing_months(monthly_table_ids, start, end, print_fn)

    qualified_destination = qualified_table_id(destination_table_id)
    select_sql = build_analytics_select(monthly_table_ids)
    print_fn(
        f"[ANALYTICS] combining {len(monthly_table_ids)} monthly table(s) -> {qualified_destination}"
    )

    if dry_run:
        try:
            bytes_estimate = estimate_bytes_processed(query_client, select_sql, config.bq_location)
        except Exception as exc:  # noqa: BLE001
            print_fn(f"[AUTH/QUERY ERROR] dry run failed: {exc}")
            return EXIT_AUTH_OR_QUERY_ERROR
        print_fn(f"[DRY RUN] destination: {qualified_destination}")
        print_fn(f"[DRY RUN] source monthly tables: {len(monthly_table_ids)}")
        print_fn(f"[DRY RUN] estimated bytes processed: {bytes_estimate}")
        return EXIT_SUCCESS

    if not validate_only:
        try:
            loader.load(
                destination_project=destination_project,
                destination_dataset=destination_dataset,
                monthly_table_ids=monthly_table_ids,
                table_name=resolved_table_name,
            )
        except Exception as exc:  # noqa: BLE001
            print_fn(f"[LOAD ERROR] {exc}")
            return EXIT_LOAD_ERROR
        print_fn(f"Loaded: {qualified_destination}")

    try:
        observed = gather_observed_analytics(
            query_client, config.bq_location, qualified_destination, monthly_table_ids
        )
    except Exception as exc:  # noqa: BLE001
        print_fn(f"[AUTH/QUERY ERROR] failed to gather observed data: {exc}")
        return EXIT_AUTH_OR_QUERY_ERROR

    result = validate_analytics(observed)

    print_fn(f"[{'PASS' if result.passed else 'FAIL'}] {qualified_destination}")
    print_fn(f"  analytics_rows: {observed.analytics_row_count}")
    print_fn(f"  source_rows:    {observed.source_row_count}")
    if result.mismatches:
        print_fn("  Mismatches:")
        for mismatch in result.mismatches:
            print_fn(f"    - {mismatch}")

    return EXIT_SUCCESS if result.passed else EXIT_VALIDATION_FAILURE
