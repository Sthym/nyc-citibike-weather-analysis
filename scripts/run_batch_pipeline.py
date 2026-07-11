#!/usr/bin/env python3
"""CLI entry point: Stage 5 multi-month batch Citi Bike + weather ETL.

Runs the SAME Stage 4 monthly pipeline (``src.pipeline.monthly_pipeline.
execute`` -- no duplicated query/load/validation logic) once per month
across a ``--start-year``/``--start-month`` .. ``--end-year``/
``--end-month`` range, after a STRICT whole-range preflight check: every
requested month must be fully covered by the live shared source range,
or nothing runs.

Usage:
    python scripts/run_batch_pipeline.py --start-year 2025 --start-month 1 --end-year 2025 --end-month 3
    python scripts/run_batch_pipeline.py --start-year 2025 --start-month 1 --end-year 2025 --end-month 3 --dry-run
    python scripts/run_batch_pipeline.py --start-year 2025 --start-month 1 --end-year 2025 --end-month 3 --validate-only
    python scripts/run_batch_pipeline.py --start-year 2025 --start-month 1 --end-year 2025 --end-month 3 --continue-on-error

Destination tables: one ``citibike_weather_monthly_{year:04d}_{month:02d}``
per month (identical Stage 4 naming), in YOUR OWN destination
project/dataset (same ``BQ_DESTINATION_PROJECT_ID`` / ``BQ_DESTINATION_
DATASET`` configuration as ``run_monthly_pipeline.py``).

Modes: ``--dry-run`` and ``--validate-only`` are mutually exclusive and
apply to every month in the range identically; neither ever issues a
``CREATE OR REPLACE TABLE``.

Failure handling: by default, the batch STOPS at the first month that
fails (subsequent months are logged as skipped, never attempted). Pass
``--continue-on-error`` to process every requested month regardless of
earlier failures.

Run log: every run writes a JSONL file to ``--log-dir`` (default:
``logs/batch_runs/`` at the repo root; gitignored -- runtime logs are
never committed). Two record types: one "month_run" record per
REQUESTED month -- whether it was actually attempted (status
success/failure, that month's own exit code) or skipped (status
skipped, a reason) -- and exactly one final "batch_summary" record with
aggregate counts, the overall exit code, and (dry-run only)
total_estimated_bytes across the whole range.

Prerequisites: identical to ``run_monthly_pipeline.py`` -- see that
script's docstring / README.md "Getting started".

Exit codes (identical to run_monthly_pipeline.py's 0-7, plus one new
batch-specific code):
  0 success -- every requested month succeeded
  1 unexpected internal error
  2 CLI usage error (bad --year/--month shape, end-before-start range,
    --dry-run/--validate-only together)
  3 configuration error
  4 invalid or unavailable month/range -- the STRICT whole-range
    preflight check failed: at least one requested month is not fully
    covered by the current live shared source range. This is Stage 4's
    OWN "invalid/unavailable month" code, reused here for the
    whole-range case; ZERO months are processed when this happens.
  5 authentication/query error
  6 load error
  7 validation failure
  8 logging failure -- the JSONL run log itself could not be written.
    Takes priority over any other outcome the moment it occurs.

When continuing past a failure (`--continue-on-error`) or stopping at
the first one (default), the returned code is 0 if everything succeeded,
otherwise the exit code of the FIRST month that failed, in chronological
order (5/6/7 -- delegated from that month's own Stage 4 result), never a
new code invented for "some months failed" -- see
src/pipeline/batch_pipeline.py.
"""
from __future__ import annotations

import argparse
import os
import sys

# Make `src` importable regardless of the current working directory.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)

from google.cloud import bigquery

from src.extraction.bigquery_client import BigQueryReadOnlyClient
from src.extraction.config import load_config
from src.loading.prototype_loader import PrototypeLoader
from src.pipeline.batch_log import JsonlBatchLogger, new_run_id
from src.pipeline.batch_period import months_in_range
from src.pipeline.batch_pipeline import execute_batch
from src.pipeline.month_period import CliUsageError, load_destination_config, parse_year_month
from src.pipeline.monthly_pipeline import (
    EXIT_CONFIG_ERROR,
    EXIT_UNEXPECTED_ERROR,
    EXIT_USAGE_ERROR,
)

DEFAULT_LOG_DIR = os.path.join(_REPO_ROOT, "logs", "batch_runs")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_batch_pipeline.py",
        description="Stage 5 multi-month batch Citi Bike + weather ETL pipeline.",
    )
    parser.add_argument("--start-year", type=int, required=True, help="e.g. 2025")
    parser.add_argument("--start-month", type=int, required=True, help="1-12")
    parser.add_argument("--end-year", type=int, required=True, help="e.g. 2025")
    parser.add_argument("--end-month", type=int, required=True, help="1-12")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="For every month: build and validate the SQL, report a live bytes-processed "
        "estimate, write nothing.",
    )
    mode.add_argument(
        "--validate-only",
        action="store_true",
        help="For every month: validate an existing destination table without replacing it.",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Process every requested month even if an earlier one fails. "
        "Default: stop at the first failure and skip the rest.",
    )
    parser.add_argument(
        "--log-dir",
        default=DEFAULT_LOG_DIR,
        help=f"Directory for the JSONL run log (default: {DEFAULT_LOG_DIR}).",
    )
    return parser


def main(argv=None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)  # argparse itself exits(2) on bad types / mutually-exclusive violation

    try:
        start_year, start_month = parse_year_month(args.start_year, args.start_month)
        end_year, end_month = parse_year_month(args.end_year, args.end_month)
        months_in_range(start_year, start_month, end_year, end_month)  # validates chronological order
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

    run_id = new_run_id()
    log_path = os.path.join(args.log_dir, f"batch_{run_id}.jsonl")
    logger = JsonlBatchLogger(path=log_path, run_id=run_id)
    print(f"[BATCH] run log: {log_path}")

    try:
        return execute_batch(
            start_year=start_year,
            start_month=start_month,
            end_year=end_year,
            end_month=end_month,
            dry_run=args.dry_run,
            validate_only=args.validate_only,
            continue_on_error=args.continue_on_error,
            config=config,
            destination_project=destination_project,
            destination_dataset=destination_dataset,
            read_client=read_client,
            query_client=query_client,
            loader=loader,
            logger=logger,
        )
    except Exception as exc:  # noqa: BLE001 -- everything categorizable is caught inside execute_batch()
        print(f"[UNEXPECTED ERROR] {exc}", file=sys.stderr)
        return EXIT_UNEXPECTED_ERROR
    finally:
        logger.close()


if __name__ == "__main__":
    raise SystemExit(main())
