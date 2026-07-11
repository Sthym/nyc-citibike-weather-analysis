"""Optional live integration checks for the Stage 4 reusable monthly
pipeline.

NOT part of the default unit-test suite (same two-layer protection as
Stage 3's tests/integration/test_prototype_live.py):
  1. `pytest.ini` sets `testpaths = tests/unit`.
  2. Every test here is `@pytest.mark.integration` and additionally
     gated behind `RUN_LIVE_BIGQUERY_TESTS=1`.

These tests exercise live source-range retrieval, `--dry-run`, and
`--validate-only` -- all read-only paths. None of them ever calls
`loader.load()` / issues a CREATE OR REPLACE TABLE: a write remains an
explicit CLI action (running scripts/run_monthly_pipeline.py without
--dry-run/--validate-only), never something a test triggers automatically.

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
    return bool(os.environ.get("GCP_PROJECT_ID"))


@pytest.mark.skipif(not _live_tests_enabled(), reason="RUN_LIVE_BIGQUERY_TESTS not set to 1")
def test_live_source_range_retrieval():
    if not _config_available():
        pytest.skip("GCP_PROJECT_ID not configured")

    from src.extraction.bigquery_client import BigQueryReadOnlyClient
    from src.extraction.config import load_config
    from src.pipeline.month_period import compute_effective_range

    config = load_config()
    read_client = BigQueryReadOnlyClient(project=config.gcp_project_id, location=config.bq_location)

    citibike_stats = read_client.get_table_row_count(config.citibike_table)
    assert citibike_stats > 0

    citibike_range = read_client.get_date_range_stats(config.citibike_table)
    weather_range = read_client.get_date_range_stats(config.weather_table)

    effective_min, effective_max = compute_effective_range(
        citibike_range["min_date"],
        citibike_range["max_date"],
        weather_range["min_date"],
        weather_range["max_date"],
    )
    assert effective_min <= effective_max


@pytest.mark.skipif(not _live_tests_enabled(), reason="RUN_LIVE_BIGQUERY_TESTS not set to 1")
def test_live_dry_run_never_writes(capsys):
    if not _config_available() or not os.environ.get("BQ_DESTINATION_DATASET"):
        pytest.skip("GCP_PROJECT_ID / BQ_DESTINATION_DATASET not configured")

    from google.cloud import bigquery

    from src.extraction.bigquery_client import BigQueryReadOnlyClient
    from src.extraction.config import load_config
    from src.loading.prototype_loader import PrototypeLoader
    from src.pipeline.month_period import load_destination_config, monthly_table_name
    from src.pipeline.monthly_pipeline import EXIT_SUCCESS, execute

    config = load_config()
    destination_project = os.environ.get("BQ_DESTINATION_PROJECT_ID") or config.gcp_project_id
    destination_dataset = os.environ["BQ_DESTINATION_DATASET"]

    read_client = BigQueryReadOnlyClient(project=config.gcp_project_id, location=config.bq_location)
    query_client = bigquery.Client(project=config.gcp_project_id)
    loader = PrototypeLoader(project=config.gcp_project_id, location=config.bq_location)

    year, month = 2025, 1
    table_name = monthly_table_name(year, month)

    result = execute(
        year=year,
        month=month,
        table_name=table_name,
        dry_run=True,
        validate_only=False,
        config=config,
        destination_project=destination_project,
        destination_dataset=destination_dataset,
        read_client=read_client,
        query_client=query_client,
        loader=loader,
    )
    assert result == EXIT_SUCCESS
    out = capsys.readouterr().out
    assert "bytes processed" in out


@pytest.mark.skipif(not _live_tests_enabled(), reason="RUN_LIVE_BIGQUERY_TESTS not set to 1")
def test_live_validate_only_does_not_require_a_load_first():
    """validate-only must never call loader.load(); if the destination
    table doesn't already exist, this is expected to fail cleanly with a
    live query error (exit 5), not attempt to create anything.
    """
    if not _config_available() or not os.environ.get("BQ_DESTINATION_DATASET"):
        pytest.skip("GCP_PROJECT_ID / BQ_DESTINATION_DATASET not configured")

    from google.cloud import bigquery

    from src.extraction.bigquery_client import BigQueryReadOnlyClient
    from src.extraction.config import load_config
    from src.loading.prototype_loader import PrototypeLoader
    from src.pipeline.month_period import monthly_table_name
    from src.pipeline.monthly_pipeline import (
        EXIT_AUTH_OR_QUERY_ERROR,
        EXIT_SUCCESS,
        EXIT_VALIDATION_FAILURE,
        execute,
    )

    config = load_config()
    destination_project = os.environ.get("BQ_DESTINATION_PROJECT_ID") or config.gcp_project_id
    destination_dataset = os.environ["BQ_DESTINATION_DATASET"]

    read_client = BigQueryReadOnlyClient(project=config.gcp_project_id, location=config.bq_location)
    query_client = bigquery.Client(project=config.gcp_project_id)

    class LoaderThatMustNeverBeCalled:
        def load(self, **kwargs):
            raise AssertionError("validate-only must never call loader.load()")

    year, month = 2025, 1
    table_name = monthly_table_name(year, month)

    result = execute(
        year=year,
        month=month,
        table_name=table_name,
        dry_run=False,
        validate_only=True,
        config=config,
        destination_project=destination_project,
        destination_dataset=destination_dataset,
        read_client=read_client,
        query_client=query_client,
        loader=LoaderThatMustNeverBeCalled(),
    )
    # Whatever the outcome (table may or may not already exist), the one
    # thing we assert is that it's a recognized, clean exit code.
    assert result in (EXIT_SUCCESS, EXIT_VALIDATION_FAILURE, EXIT_AUTH_OR_QUERY_ERROR)
