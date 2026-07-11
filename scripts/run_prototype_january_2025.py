#!/usr/bin/env python3
"""CLI entry point: Stage 3 one-month (January 2025) ETL prototype.

This is the ONLY module in Stage 3 that touches live BigQuery. It:
  1. Loads the prototype join (Citi Bike full 15-column shape + 8 curated
     weather fields) into the caller's own destination project/dataset
     via ``CREATE OR REPLACE TABLE`` (idempotent -- safe to re-run).
  2. Re-reads both the destination table and the two source tables
     (scoped to January 2025 only, using query parameters -- no date
     literals embedded in SQL text) to gather the "observed" data the
     V1-V11 rules need.
  3. Runs ``validate_prototype`` (pure logic, unit-tested separately in
     tests/unit/test_prototype_validator.py) and prints a PASS/FAIL
     report, including matched/unmatched weather rows and the weather
     match rate, plus any V8/V9 source-quality findings (reported, never
     treated as failures, source values never altered).

Prerequisites:
  - `gcloud auth application-default login` has been run locally
  - GCP_PROJECT_ID is set (your own billing/query-execution project)
  - BQ_DESTINATION_DATASET is set to an EXISTING dataset in your own
    project (this script never creates a dataset)
  - BQ_DESTINATION_PROJECT_ID may be set to write to a project other
    than GCP_PROJECT_ID; otherwise it defaults to GCP_PROJECT_ID

Usage:
    python scripts/run_prototype_january_2025.py
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Mapping, Optional

# Make `src` importable regardless of the current working directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google.cloud import bigquery

from src.extraction.config import load_config
from src.extraction.table_id import validate_table_id
from src.loading.prototype_loader import PrototypeLoader, prototype_table_name
from src.transformation.prototype_query import month_range
from src.transformation.prototype_validator import (
    ADDITIVE_CITIBIKE_COLUMNS,
    ObservedPrototypeData,
    cast_int_indicator_to_bool,
    validate_prototype,
)

YEAR = 2025
MONTH = 1

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


def load_destination_config(
    env: Optional[Mapping[str, str]] = None, default_project: Optional[str] = None
) -> tuple[str, str]:
    """Read the Stage 3 destination project/dataset from the environment.

    ``BQ_DESTINATION_DATASET`` is required and must name a dataset that
    already exists in the destination project -- this script never
    creates one. ``BQ_DESTINATION_PROJECT_ID`` falls back to
    ``default_project`` (normally ``GCP_PROJECT_ID``) if unset.
    """
    source = os.environ if env is None else env

    destination_dataset = source.get("BQ_DESTINATION_DATASET")
    if not destination_dataset:
        raise ValueError(
            "BQ_DESTINATION_DATASET is required and must name an EXISTING "
            "dataset in your own project -- this script never creates one."
        )

    destination_project = source.get("BQ_DESTINATION_PROJECT_ID") or default_project
    if not destination_project:
        raise ValueError(
            "BQ_DESTINATION_PROJECT_ID or GCP_PROJECT_ID must be set to "
            "determine which project to write the prototype table into."
        )

    return destination_project, destination_dataset


def _additive_sum_sql(table: str, where_clause: str = "") -> str:
    select_list = ",\n  ".join(f"SUM({c}) AS {c}" for c in ADDITIVE_CITIBIKE_COLUMNS)
    sql = f"SELECT\n  {select_list}\nFROM `{table}`"
    if where_clause:
        sql += f"\n{where_clause}"
    return sql


def _run_query(
    client: bigquery.Client,
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
    query_job = client.query(sql, job_config=job_config, location=location)
    return list(query_job.result())


def _qualified(table_id: str) -> str:
    ref = validate_table_id(table_id)
    return f"{ref.project}.{ref.dataset_id}.{ref.table_id}"


def main() -> int:
    config = load_config()
    destination_project, destination_dataset = load_destination_config(
        default_project=config.gcp_project_id
    )

    rng = month_range(YEAR, MONTH)
    print(f"Stage 3 prototype: {YEAR}-{MONTH:02d} ({rng.start_date} .. {rng.end_date})")
    print(
        f"Destination: {destination_project}.{destination_dataset}."
        f"{prototype_table_name(YEAR, MONTH)}"
    )

    loader = PrototypeLoader(project=config.gcp_project_id, location=config.bq_location)
    destination_ref = loader.load(
        destination_project=destination_project,
        destination_dataset=destination_dataset,
        year=YEAR,
        month=MONTH,
        citibike_table=config.citibike_table,
        weather_table=config.weather_table,
        start_date=rng.start_date,
        end_date=rng.end_date,
    )
    qualified_destination = (
        f"{destination_ref.project}.{destination_ref.dataset_id}.{destination_ref.table_id}"
    )
    print(f"Loaded: {qualified_destination}")

    client = bigquery.Client(project=config.gcp_project_id)
    location = config.bq_location
    qualified_citibike = _qualified(config.citibike_table)
    qualified_weather = _qualified(config.weather_table)

    # --- Destination structural stats ---
    structural = _run_query(
        client, STRUCTURAL_SQL_TEMPLATE.format(table=qualified_destination), location
    )[0]

    # --- Additive sums: destination vs. Citi Bike source (scoped to month) ---
    destination_additive_sums: Dict[str, float] = dict(
        _run_query(client, _additive_sum_sql(qualified_destination), location)[0].items()
    )
    source_additive_sums: Dict[str, float] = dict(
        _run_query(
            client,
            _additive_sum_sql(
                qualified_citibike, where_clause="WHERE date BETWEEN @start_date AND @end_date"
            ),
            location,
            rng.start_date,
            rng.end_date,
        )[0].items()
    )

    # --- Citi Bike source row count, scoped to month ---
    citibike_source_row_count = _run_query(
        client,
        f"SELECT COUNT(*) AS row_count FROM `{qualified_citibike}` "
        "WHERE date BETWEEN @start_date AND @end_date",
        location,
        rng.start_date,
        rng.end_date,
    )[0]["row_count"]

    # --- Destination per-date rows ---
    destination_rows_by_date: Dict[Any, Dict[str, Any]] = {}
    for row in _run_query(
        client, DESTINATION_ROWS_SQL_TEMPLATE.format(table=qualified_destination), location
    ):
        row_dict = dict(row.items())
        destination_rows_by_date[row_dict["date"]] = row_dict

    # --- Citi Bike source per-date rows (non-additive + reconciliation) ---
    citibike_source_rows_by_date: Dict[Any, Dict[str, Any]] = {}
    citibike_reconciliation_rows: List[Dict[str, Any]] = []
    for row in _run_query(
        client,
        CITIBIKE_ROWS_SQL_TEMPLATE.format(table=qualified_citibike),
        location,
        rng.start_date,
        rng.end_date,
    ):
        row_dict = dict(row.items())
        citibike_source_rows_by_date[row_dict["date"]] = row_dict
        citibike_reconciliation_rows.append(row_dict)

    # --- Weather source per-date rows ---
    # weather_indicator_rows keeps the RAW (un-cast) is_rainy/is_snowy
    # values for V11's domain check. weather_source_rows_by_date carries
    # the BOOL-cast versions (mirroring CAST(source.is_rainy AS BOOL))
    # for the V10 row-by-row comparison against the destination.
    weather_source_rows_by_date: Dict[Any, Dict[str, Any]] = {}
    weather_indicator_rows: List[Dict[str, Any]] = []
    for row in _run_query(
        client,
        WEATHER_ROWS_SQL_TEMPLATE.format(table=qualified_weather),
        location,
        rng.start_date,
        rng.end_date,
    ):
        row_dict = dict(row.items())
        weather_indicator_rows.append(dict(row_dict))
        cast_row = dict(row_dict)
        cast_row["is_rainy"] = cast_int_indicator_to_bool(row_dict["is_rainy"])
        cast_row["is_snowy"] = cast_int_indicator_to_bool(row_dict["is_snowy"])
        weather_source_rows_by_date[row_dict["date"]] = cast_row

    observed = ObservedPrototypeData(
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

    result = validate_prototype(observed, rng.start_date, rng.end_date)

    print()
    print(f"[{'PASS' if result.passed else 'FAIL'}] Stage 3 prototype validation")
    print(f"  matched_weather_rows:   {result.matched_weather_rows}")
    print(f"  unmatched_weather_rows: {result.unmatched_weather_rows}")
    if result.weather_match_rate is not None:
        print(f"  weather_match_rate:     {result.weather_match_rate:.4f}")
    if result.mismatches:
        print("  Mismatches:")
        for m in result.mismatches:
            print(f"    - {m}")
    if result.source_quality_findings:
        print("  Source-quality findings (reported, not failures; source values unchanged):")
        for finding in result.source_quality_findings:
            print(f"    - {finding}")

    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
