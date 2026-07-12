#!/usr/bin/env python3
"""CLI entry point: Stage 6 dashboard-ready analytics table.

Combines the EXISTING Stage 4/5 monthly destination tables
(``citibike_weather_monthly_YYYY_MM``) in YOUR OWN destination project/
dataset into ONE daily-grain analytics table
(``citibike_weather_analytics``), adding the dashboard-friendly derived
fields ``temperature_band`` / ``rain_category`` / ``snow_category``. It
reads the monthly DESTINATION tables, never the raw public sources.

Usage:
    python scripts/build_analytics_table.py
    python scripts/build_analytics_table.py --dry-run
    python scripts/build_analytics_table.py --validate-only
    python scripts/build_analytics_table.py --start 2025-01 --end 2025-06

Destination: one fixed ``citibike_weather_analytics`` table (name is not
user-supplied, so re-runs always overwrite it via CREATE OR REPLACE), in
the same ``BQ_DESTINATION_PROJECT_ID`` / ``BQ_DESTINATION_DATASET``
configuration used by ``run_monthly_pipeline.py`` /
``run_batch_pipeline.py``. The destination dataset is never auto-created.

Modes: ``--dry-run`` and ``--validate-only`` are mutually exclusive.
``--dry-run`` builds the SQL and reports a live bytes-processed estimate,
writing nothing. ``--validate-only`` runs the A1-A11 validation against
an already-existing analytics table without replacing it.

``--start`` / ``--end`` (``YYYY-MM``) optionally restrict which monthly
tables are combined; months in that window with no monthly table are
reported as warnings, not failures. Omit both to combine every monthly
table found.

Prerequisites: identical to ``run_monthly_pipeline.py`` -- Application
Default Credentials (``gcloud auth application-default login``), no
service-account keys; see that script's docstring / README.md.

Exit codes (reuses the shared scheme; see
``src/pipeline/monthly_pipeline.py`` and ``DECISIONS.md`` D-028):
  0 success -- analytics table built (or validated) and A1-A11 passed
  1 unexpected internal error
  2 CLI usage error (bad --start/--end shape, --dry-run/--validate-only
    together)
  3 configuration error
  4 no monthly tables found to combine (reuses Stage 4's
    invalid/unavailable-input code; nothing is written)
  5 authentication/query error
  6 load error
  7 validation failure (A1-A11)
(Exit code 8 is Stage 5's logging-failure code and is not used here --
Stage 6 writes no run log.)
"""
from __future__ import annotations

import argparse
import os
import sys

# Make `src` importable regardless of the current working directory.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)

from google.cloud import bigquery

from src.analytics.analytics_pipeline import execute
from src.extraction.config import load_config
from src.loading.analytics_loader import AnalyticsLoader
from src.pipeline.month_period import CliUsageError, load_destination_config
from src.pipeline.monthly_pipeline import (
    EXIT_CONFIG_ERROR,
    EXIT_UNEXPECTED_ERROR,
    EXIT_USAGE_ERROR,
)


def parse_year_month_arg(value: str, flag: str):
    """Parse a ``YYYY-MM`` CLI argument into a ``(year, month)`` tuple.

    Raises ``CliUsageError`` (exit code 2) for anything malformed -- a
    pure input-shape problem, distinct from an unavailable month.
    """
    parts = value.split("-")
    if len(parts) != 2:
        raise CliUsageError(f"{flag} must be in YYYY-MM form, got {value!r}")
    try:
        year = int(parts[0])
        month = int(parts[1])
    except ValueError:
        raise CliUsageError(f"{flag} must be in YYYY-MM form, got {value!r}") from None
    if not (1 <= month <= 12):
        raise CliUsageError(f"{flag} month must be between 1 and 12, got {month}")
    return year, month


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="build_analytics_table.py",
        description="Stage 6: build the dashboard-ready daily analytics table from the monthly tables.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Build and validate the SQL, report a live bytes-processed estimate, write nothing.",
    )
    mode.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate an existing analytics table (A1-A11) without replacing it.",
    )
    parser.add_argument("--start", help="Earliest monthly table to combine, YYYY-MM (optional).")
    parser.add_argument("--end", help="Latest monthly table to combine, YYYY-MM (optional).")
    return parser


def main(argv=None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)  # argparse itself exits(2) on mutually-exclusive violation

    try:
        start = parse_year_month_arg(args.start, "--start") if args.start else None
        end = parse_year_month_arg(args.end, "--end") if args.end else None
        if start is not None and end is not None and end < start:
            raise CliUsageError(f"--end ({args.end}) must not be before --start ({args.start})")
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
        discovery_client = bigquery.Client(project=config.gcp_project_id)
        query_client = bigquery.Client(project=config.gcp_project_id)
        loader = AnalyticsLoader(project=config.gcp_project_id, location=config.bq_location)
    except Exception as exc:  # noqa: BLE001
        print(f"[CONFIG ERROR] failed to construct BigQuery clients: {exc}", file=sys.stderr)
        return EXIT_CONFIG_ERROR

    try:
        return execute(
            dry_run=args.dry_run,
            validate_only=args.validate_only,
            config=config,
            destination_project=destination_project,
            destination_dataset=destination_dataset,
            discovery_client=discovery_client,
            query_client=query_client,
            loader=loader,
            start=start,
            end=end,
        )
    except Exception as exc:  # noqa: BLE001 -- everything categorizable is caught inside execute()
        print(f"[UNEXPECTED ERROR] {exc}", file=sys.stderr)
        return EXIT_UNEXPECTED_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
