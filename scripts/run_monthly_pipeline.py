#!/usr/bin/env python3
"""CLI entry point: Stage 4 reusable monthly ETL pipeline.

Generalizes the Stage 3 January-2025-only prototype so the SAME query
builder, loader, and validator (all unchanged from Stage 3) can process
any valid month via ``--year``/``--month``, with no Python or SQL source
changes required per month.

Usage:
    python scripts/run_monthly_pipeline.py --year 2025 --month 2
    python scripts/run_monthly_pipeline.py --year 2025 --month 2 --dry-run
    python scripts/run_monthly_pipeline.py --year 2025 --month 2 --validate-only

Destination table: citibike_weather_monthly_{year:04d}_{month:02d} in
YOUR OWN destination project/dataset (BQ_DESTINATION_PROJECT_ID falls
back to GCP_PROJECT_ID; BQ_DESTINATION_DATASET is required, never
auto-created). This is a DIFFERENT naming convention from Stage 3's
``citibike_weather_prototype_2025_01`` -- that table is preserved
separately; see scripts/run_prototype_january_2025.py.

--dry-run and --validate-only are mutually exclusive. Neither one ever
issues a CREATE OR REPLACE TABLE -- see src/pipeline/monthly_pipeline.py
for the exact order of operations and exit codes.

Prerequisites:
  - `gcloud auth application-default login` has been run locally
  - GCP_PROJECT_ID is set (your own billing/query-execution project)
  - BQ_DESTINATION_DATASET is set to an EXISTING dataset in your own
    project (this script never creates a dataset)

Exit codes:
  0 success
  1 unexpected error
  2 CLI usage error
  3 configuration error
  4 invalid/unavailable month
  5 authentication/query error
  6 load error
  7 validation failure
"""
from __future__ import annotations

import argparse
import os
import sys

# Make `src` importable regardless of the current working directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google.cloud import bigquery

from src.extraction.bigquery_client import BigQueryReadOnlyClient
from src.extraction.config import load_config
from src.loading.prototype_loader import PrototypeLoader
from src.pipeline.month_period import (
    CliUsageError,
    load_destination_config,
    monthly_table_name,
    parse_year_month,
)
from src.pipeline.monthly_pipeline import (
    EXIT_CONFIG_ERROR,
    EXIT_UNEXPECTED_ERROR,
    EXIT_USAGE_ERROR,
    execute,
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_monthly_pipeline.py",
        description="Stage 4 reusable monthly Citi Bike + weather ETL pipeline.",
    )
    parser.add_argument("--year", type=int, required=True, help="e.g. 2025")
    parser.add_argument("--month", type=int, required=True, help="1-12")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Build and validate the SQL, report a live bytes-processed estimate, write nothing.",
    )
    mode.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate an existing destination table without replacing it.",
    )
    return parser


def main(argv=None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)  # argparse itself exits(2) on bad types / mutually-exclusive violation

    try:
        year, month = parse_year_month(args.year, args.month)
    except CliUsageError as exc:
        print(f"[USAGE ERROR] {exc}", file=sys.stderr)
        return EXIT_USAGE_ERROR

    try:
        config = load_config()
        destination_project, destination_dataset = load_destination_config(
            default_project=config.gcp_project_id
        )
    except ValueError as exc:
        print(f"[CONFIG ERROR] {exc}", file=sys.stderr)
        return EXIT_CONFIG_ERROR

    try:
        read_client = BigQueryReadOnlyClient(project=config.gcp_project_id, location=config.bq_location)
        query_client = bigquery.Client(project=config.gcp_project_id)
        loader = PrototypeLoader(project=config.gcp_project_id, location=config.bq_location)
    except Exception as exc:  # noqa: BLE001
        print(f"[CONFIG ERROR] failed to construct BigQuery clients: {exc}", file=sys.stderr)
        return EXIT_CONFIG_ERROR

    table_name = monthly_table_name(year, month)

    try:
        return execute(
            year=year,
            month=month,
            table_name=table_name,
            dry_run=args.dry_run,
            validate_only=args.validate_only,
            config=config,
            destination_project=destination_project,
            destination_dataset=destination_dataset,
            read_client=read_client,
            query_client=query_client,
            loader=loader,
        )
    except Exception as exc:  # noqa: BLE001 -- everything categorizable is caught inside execute()
        print(f"[UNEXPECTED ERROR] {exc}", file=sys.stderr)
        return EXIT_UNEXPECTED_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
