"""Optional live integration check for the Stage 3 one-month prototype.

This test is NOT part of the default unit-test suite, protected two ways:
  1. `pytest.ini` sets `testpaths = tests/unit`, so a bare
     `pytest` / `python -m pytest` invocation never even collects this
     file.
  2. Every test here is marked `@pytest.mark.integration` and additionally
     gated behind the `RUN_LIVE_BIGQUERY_TESTS=1` environment variable,
     so even an explicit `pytest tests/integration` run skips cleanly
     without it.

It writes a real `CREATE OR REPLACE TABLE` into your own destination
project/dataset -- run it deliberately, not by accident:

    RUN_LIVE_BIGQUERY_TESTS=1 python -m pytest tests/integration -m integration -v

Requires the same prerequisites as scripts/run_prototype_january_2025.py:
`gcloud auth application-default login`, GCP_PROJECT_ID, and
BQ_DESTINATION_DATASET (an EXISTING dataset -- this test never creates one).
"""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.integration


def _live_tests_enabled() -> bool:
    return os.environ.get("RUN_LIVE_BIGQUERY_TESTS") == "1"


@pytest.mark.skipif(not _live_tests_enabled(), reason="RUN_LIVE_BIGQUERY_TESTS not set to 1")
def test_prototype_load_creates_expected_table():
    if not os.environ.get("GCP_PROJECT_ID") or not os.environ.get("BQ_DESTINATION_DATASET"):
        pytest.skip("GCP_PROJECT_ID / BQ_DESTINATION_DATASET not configured")

    from src.extraction.config import load_config
    from src.loading.prototype_loader import PrototypeLoader, prototype_table_name
    from src.transformation.prototype_query import month_range

    config = load_config()
    destination_project = os.environ.get("BQ_DESTINATION_PROJECT_ID") or config.gcp_project_id
    destination_dataset = os.environ["BQ_DESTINATION_DATASET"]

    loader = PrototypeLoader(project=config.gcp_project_id, location=config.bq_location)
    rng = month_range(2025, 1)

    ref = loader.load(
        destination_project=destination_project,
        destination_dataset=destination_dataset,
        year=2025,
        month=1,
        citibike_table=config.citibike_table,
        weather_table=config.weather_table,
        start_date=rng.start_date,
        end_date=rng.end_date,
    )

    assert ref.table_id == prototype_table_name(2025, 1)
    assert ref.project == destination_project
    assert ref.dataset_id == destination_dataset

    # Full observed-data gathering + validate_prototype(...) reporting is
    # exercised by scripts/run_prototype_january_2025.py, which prints a
    # complete PASS/FAIL report. Re-implementing that query logic here
    # would duplicate the script rather than test something new; this
    # test's job is narrower -- prove the idempotent load path itself
    # works end-to-end against real BigQuery.
    query_job = loader._client.query(  # noqa: SLF001 -- intentional, read-only sanity check
        f"SELECT COUNT(*) AS row_count FROM `{ref.project}.{ref.dataset_id}.{ref.table_id}`",
        location=config.bq_location,
    )
    row_count = list(query_job.result())[0]["row_count"]
    assert row_count > 0


@pytest.mark.skipif(not _live_tests_enabled(), reason="RUN_LIVE_BIGQUERY_TESTS not set to 1")
def test_prototype_load_is_idempotent_on_rerun():
    """Running the load twice must not duplicate rows (CTAS fully
    replaces the table contents each time)."""
    if not os.environ.get("GCP_PROJECT_ID") or not os.environ.get("BQ_DESTINATION_DATASET"):
        pytest.skip("GCP_PROJECT_ID / BQ_DESTINATION_DATASET not configured")

    from src.extraction.config import load_config
    from src.loading.prototype_loader import PrototypeLoader
    from src.transformation.prototype_query import month_range

    config = load_config()
    destination_project = os.environ.get("BQ_DESTINATION_PROJECT_ID") or config.gcp_project_id
    destination_dataset = os.environ["BQ_DESTINATION_DATASET"]

    loader = PrototypeLoader(project=config.gcp_project_id, location=config.bq_location)
    rng = month_range(2025, 1)

    load_kwargs = dict(
        destination_project=destination_project,
        destination_dataset=destination_dataset,
        year=2025,
        month=1,
        citibike_table=config.citibike_table,
        weather_table=config.weather_table,
        start_date=rng.start_date,
        end_date=rng.end_date,
    )

    ref_first = loader.load(**load_kwargs)
    query_job = loader._client.query(  # noqa: SLF001
        f"SELECT COUNT(*) AS row_count FROM `{ref_first.project}.{ref_first.dataset_id}.{ref_first.table_id}`",
        location=config.bq_location,
    )
    first_count = list(query_job.result())[0]["row_count"]

    ref_second = loader.load(**load_kwargs)
    query_job = loader._client.query(  # noqa: SLF001
        f"SELECT COUNT(*) AS row_count FROM `{ref_second.project}.{ref_second.dataset_id}.{ref_second.table_id}`",
        location=config.bq_location,
    )
    second_count = list(query_job.result())[0]["row_count"]

    assert first_count == second_count
