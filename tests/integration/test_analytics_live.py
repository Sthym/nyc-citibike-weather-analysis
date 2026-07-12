"""Optional live integration checks for the Stage 6 analytics build.

NOT part of the default unit-test suite (same two-layer protection as the
Stage 3/4/5 live tests):
  1. `pytest.ini` sets `testpaths = tests/unit`.
  2. Every test here is `@pytest.mark.integration` and additionally
     gated behind `RUN_LIVE_BIGQUERY_TESTS=1`.

These tests exercise a live `--dry-run` and a live `--validate-only`
analytics build -- both read-only paths. Neither ever calls
`loader.load()` / issues a `CREATE OR REPLACE TABLE`: an analytics-table
write remains an explicit CLI action (running
scripts/build_analytics_table.py with no --dry-run/--validate-only),
never something a test triggers automatically. The dataset must already
contain at least one `citibike_weather_monthly_YYYY_MM` table (built by
Stage 4/5); nothing here creates one.

Run explicitly with:
    RUN_LIVE_BIGQUERY_TESTS=1 python -m pytest tests/integration -m integration -v
"""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.integration


def _live_tests_enabled() -> bool:
    return os.environ.get("RUN_LIVE_BIGQUERY_TESTS") == "1"


def _config_available() -> bool:
    return bool(os.environ.get("GCP_PROJECT_ID")) and bool(os.environ.get("BQ_DESTINATION_DATASET"))


class _LoaderThatMustNeverBeCalled:
    def load(self, **kwargs):
        raise AssertionError("read-only mode must never call loader.load()")


def _run(dry_run, validate_only):
    from google.cloud import bigquery

    from src.analytics.analytics_pipeline import execute
    from src.extraction.config import load_config

    config = load_config()
    destination_project = os.environ.get("BQ_DESTINATION_PROJECT_ID") or config.gcp_project_id
    destination_dataset = os.environ["BQ_DESTINATION_DATASET"]

    query_client = bigquery.Client(project=config.gcp_project_id)
    discovery_client = bigquery.Client(project=config.gcp_project_id)

    return execute(
        dry_run=dry_run,
        validate_only=validate_only,
        config=config,
        destination_project=destination_project,
        destination_dataset=destination_dataset,
        discovery_client=discovery_client,
        query_client=query_client,
        loader=_LoaderThatMustNeverBeCalled(),
    )


@pytest.mark.skipif(not _live_tests_enabled(), reason="RUN_LIVE_BIGQUERY_TESTS not set to 1")
def test_live_dry_run_never_writes():
    if not _config_available():
        pytest.skip("GCP_PROJECT_ID / BQ_DESTINATION_DATASET not configured")
    from src.analytics.analytics_pipeline import EXIT_SUCCESS, EXIT_NO_SOURCE_TABLES

    result = _run(dry_run=True, validate_only=False)
    # Success when monthly tables exist; a clean "nothing to combine" (4)
    # is also acceptable in an empty dataset. Either way, no write occurs.
    assert result in (EXIT_SUCCESS, EXIT_NO_SOURCE_TABLES)


@pytest.mark.skipif(not _live_tests_enabled(), reason="RUN_LIVE_BIGQUERY_TESTS not set to 1")
def test_live_validate_only_never_writes():
    if not _config_available():
        pytest.skip("GCP_PROJECT_ID / BQ_DESTINATION_DATASET not configured")
    from src.analytics.analytics_pipeline import (
        EXIT_SUCCESS,
        EXIT_VALIDATION_FAILURE,
        EXIT_NO_SOURCE_TABLES,
    )

    # Validate-only against an already-built analytics table. Any of
    # pass / validation-failure / no-source-tables is a legitimate live
    # outcome; the point is that no CREATE OR REPLACE is ever issued.
    result = _run(dry_run=False, validate_only=True)
    assert result in (EXIT_SUCCESS, EXIT_VALIDATION_FAILURE, EXIT_NO_SOURCE_TABLES)
