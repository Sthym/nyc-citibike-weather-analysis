#!/usr/bin/env python3
"""CLI entry point: validate the two provided BigQuery source tables'
metadata against verified Stage 1 findings.

This is the ONLY module in the Stage 2 extraction foundation that
touches live BigQuery. It performs read-only metadata and aggregate
checks -- no full-table download, no transformation, no destination
tables.

Prerequisites:
  - `gcloud auth application-default login` has been run locally
  - GCP_PROJECT_ID is set in the environment (see config/.env.example)

Usage:
    python scripts/validate_source_metadata.py
"""
from __future__ import annotations

import os
import sys

# Make `src` importable regardless of the current working directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.extraction.bigquery_client import BigQueryReadOnlyClient
from src.extraction.config import load_config
from src.extraction.metadata_validator import (
    CITIBIKE_EXPECTED,
    WEATHER_EXPECTED,
    validate_table_metadata,
)


def _check_table(client: BigQueryReadOnlyClient, table_id: str, expected) -> bool:
    row_count = client.get_table_row_count(table_id)
    stats = client.get_date_range_stats(table_id)
    observed = {"row_count": row_count, **stats}
    result = validate_table_metadata(table_id, observed, expected)

    status = "PASS" if result.passed else "FAIL"
    print(f"[{status}] {table_id}")
    print(f"  observed: {result.observed}")
    if not result.passed:
        for mismatch in result.mismatches:
            print(f"  - {mismatch}")
    return result.passed


def main() -> int:
    config = load_config()
    client = BigQueryReadOnlyClient(
        project=config.gcp_project_id, location=config.bq_location
    )

    citibike_ok = _check_table(client, config.citibike_table, CITIBIKE_EXPECTED)
    weather_ok = _check_table(client, config.weather_table, WEATHER_EXPECTED)

    return 0 if (citibike_ok and weather_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
