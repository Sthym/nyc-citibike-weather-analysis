#!/usr/bin/env python3
"""Stage 3 compatibility wrapper -- January 2025 prototype.

Kept intentionally (NOT deleted) so this exact entry point keeps
working. As of Stage 4, this is a thin wrapper around the generalized
``src.pipeline.monthly_pipeline.execute`` with ``year=2025``,
``month=1`` fixed, using the ORIGINAL Stage 3 destination table name
(``citibike_weather_prototype_2025_01``, via
``prototype_table_name`` -- NOT Stage 4's ``citibike_weather_monthly_*``
naming) so the existing Stage 3 artifact stays a separate, undisturbed
table from anything the general Stage 4 CLI produces.

All actual logic (query building, loading, validation, exit codes) now
lives in ``src.pipeline.monthly_pipeline`` and is shared with
``scripts/run_monthly_pipeline.py`` -- nothing is duplicated here.

Usage:
    python scripts/run_prototype_january_2025.py
    python scripts/run_prototype_january_2025.py --dry-run
    python scripts/run_prototype_january_2025.py --validate-only

Exit codes: see src/pipeline/monthly_pipeline.py (0 success, 1 unexpected
error, 3 configuration error, 4 invalid/unavailable month, 5
authentication/query error, 6 load error, 7 validation failure -- 2,
CLI usage error, is unused here since this wrapper takes no --year/
--month).
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
from src.loading.prototype_loader import PrototypeLoader, prototype_table_name
from src.pipeline.month_period import load_destination_config
from src.pipeline.monthly_pipeline import EXIT_CONFIG_ERROR, EXIT_UNEXPECTED_ERROR, execute

YEAR = 2025
MONTH = 1


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_prototype_january_2025.py",
        description="Stage 3 compatibility wrapper (January 2025 only). "
        "See scripts/run_monthly_pipeline.py for any other month.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--validate-only", action="store_true")
    return parser


def main(argv=None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

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

    # Preserves the ORIGINAL Stage 3 naming -- a separate table from
    # anything scripts/run_monthly_pipeline.py produces for the same month.
    table_name = prototype_table_name(YEAR, MONTH)

    try:
        return execute(
            year=YEAR,
            month=MONTH,
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
    except Exception as exc:  # noqa: BLE001
        print(f"[UNEXPECTED ERROR] {exc}", file=sys.stderr)
        return EXIT_UNEXPECTED_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
