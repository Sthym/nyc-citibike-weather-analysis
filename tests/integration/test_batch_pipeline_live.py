"""Optional live integration checks for the Stage 5 batch pipeline.

NOT part of the default unit-test suite (same two-layer protection as
Stage 3/4's live tests):
  1. `pytest.ini` sets `testpaths = tests/unit`.
  2. Every test here is `@pytest.mark.integration` and additionally
     gated behind `RUN_LIVE_BIGQUERY_TESTS=1`.

These tests exercise a live multi-month `--dry-run` and a live
`--validate-only` batch -- both read-only paths. Neither ever calls
`loader.load()` / issues a `CREATE OR REPLACE TABLE`: a write remains an
explicit CLI action (running scripts/run_batch_pipeline.py without
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
def test_live_batch_dry_run_two_months_never_writes(tmp_path, capsys):
    if not _config_available() or not os.environ.get("BQ_DESTINATION_DATASET"):
        pytest.skip("GCP_PROJECT_ID / BQ_DESTINATION_DATASET not configured")

    from google.cloud import bigquery

    from src.extraction.bigquery_client import BigQueryReadOnlyClient
    from src.extraction.config import load_config
    from src.pipeline.batch_log import JsonlBatchLogger
    from src.pipeline.batch_pipeline import execute_batch
    from src.pipeline.monthly_pipeline import EXIT_SUCCESS

    config = load_config()
    destination_project = os.environ.get("BQ_DESTINATION_PROJECT_ID") or config.gcp_project_id
    destination_dataset = os.environ["BQ_DESTINATION_DATASET"]

    read_client = BigQueryReadOnlyClient(project=config.gcp_project_id, location=config.bq_location)
    query_client = bigquery.Client(project=config.gcp_project_id)
    logger = JsonlBatchLogger(path=str(tmp_path / "batch_live_dry_run.jsonl"), run_id="live-test-dry-run")

    class LoaderThatMustNeverBeCalled:
        def load(self, **kwargs):
            raise AssertionError("--dry-run must never call loader.load()")

    result = execute_batch(
        start_year=2025,
        start_month=1,
        end_year=2025,
        end_month=2,
        dry_run=True,
        validate_only=False,
        continue_on_error=False,
        config=config,
        destination_project=destination_project,
        destination_dataset=destination_dataset,
        read_client=read_client,
        query_client=query_client,
        loader=LoaderThatMustNeverBeCalled(),
        logger=logger,
    )
    logger.close()

    assert result == EXIT_SUCCESS
    out = capsys.readouterr().out
    assert "bytes processed" in out


@pytest.mark.skipif(not _live_tests_enabled(), reason="RUN_LIVE_BIGQUERY_TESTS not set to 1")
def test_live_batch_validate_only_never_calls_loader(tmp_path):
    """validate-only must never call loader.load() for any month; if a
    destination table doesn't already exist, that month is expected to
    fail cleanly with a live query error (exit 5), not attempt to create
    anything -- same contract as the Stage 4 live test.
    """
    if not _config_available() or not os.environ.get("BQ_DESTINATION_DATASET"):
        pytest.skip("GCP_PROJECT_ID / BQ_DESTINATION_DATASET not configured")

    from google.cloud import bigquery

    from src.extraction.bigquery_client import BigQueryReadOnlyClient
    from src.extraction.config import load_config
    from src.pipeline.batch_log import JsonlBatchLogger
    from src.pipeline.batch_pipeline import execute_batch
    from src.pipeline.monthly_pipeline import (
        EXIT_AUTH_OR_QUERY_ERROR,
        EXIT_SUCCESS,
        EXIT_VALIDATION_FAILURE,
    )

    config = load_config()
    destination_project = os.environ.get("BQ_DESTINATION_PROJECT_ID") or config.gcp_project_id
    destination_dataset = os.environ["BQ_DESTINATION_DATASET"]

    read_client = BigQueryReadOnlyClient(project=config.gcp_project_id, location=config.bq_location)
    query_client = bigquery.Client(project=config.gcp_project_id)
    logger = JsonlBatchLogger(
        path=str(tmp_path / "batch_live_validate_only.jsonl"), run_id="live-test-validate-only"
    )

    class LoaderThatMustNeverBeCalled:
        def load(self, **kwargs):
            raise AssertionError("--validate-only must never call loader.load()")

    result = execute_batch(
        start_year=2025,
        start_month=1,
        end_year=2025,
        end_month=1,
        dry_run=False,
        validate_only=True,
        continue_on_error=True,
        config=config,
        destination_project=destination_project,
        destination_dataset=destination_dataset,
        read_client=read_client,
        query_client=query_client,
        loader=LoaderThatMustNeverBeCalled(),
        logger=logger,
    )
    logger.close()

    # Whatever the per-month outcome (the table may or may not already
    # exist), the one thing asserted is a recognized, clean exit code.
    assert result in (EXIT_SUCCESS, EXIT_VALIDATION_FAILURE, EXIT_AUTH_OR_QUERY_ERROR)
