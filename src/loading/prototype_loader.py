"""Loads the Stage 3 one-month prototype into the caller's own BigQuery
destination project/dataset.

Controls preserved from design approval:
  - Destination project and dataset are always explicit arguments --
    never a hardcoded default, never inferred silently.
  - The destination dataset is NEVER auto-created. If it doesn't exist,
    the ``CREATE OR REPLACE TABLE`` statement fails with BigQuery's own
    "not found" error rather than this code creating one.
  - The destination table name is derived (``citibike_weather_prototype_
    YYYY_MM``), not user-supplied, so a caller cannot point this at an
    arbitrary/unrelated table.
  - Idempotent: ``CREATE OR REPLACE TABLE ... AS SELECT`` fully replaces
    the table's contents in one atomic statement. Re-running never
    appends duplicates.
  - ``@start_date`` / ``@end_date`` are bound as real BigQuery query
    parameters, never interpolated into the SQL text.
  - Authenticates via Application Default Credentials only (same as
    Stage 2) -- no service-account key file read or referenced.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from google.cloud import bigquery

from src.extraction.table_id import validate_table_id
from src.transformation.prototype_query import build_prototype_query


def prototype_table_name(year: int, month: int) -> str:
    """Derive the destination table name for a given prototype month."""
    return f"citibike_weather_prototype_{year:04d}_{month:02d}"


class PrototypeLoader:
    """Wraps a ``google.cloud.bigquery.Client`` for the one write this
    project performs: the prototype CTAS load.

    ``client`` can be injected (e.g. a fake) for testing without any
    network access, matching the pattern used by
    ``src.extraction.bigquery_client.BigQueryReadOnlyClient``.
    """

    def __init__(self, project: str, location: str = "US", client: Optional[bigquery.Client] = None):
        self.project = project
        self.location = location
        self._client = client or bigquery.Client(project=project)

    def build_load_ddl(
        self,
        *,
        destination_project: str,
        destination_dataset: str,
        year: int,
        month: int,
        citibike_table: str,
        weather_table: str,
        table_name: Optional[str] = None,
    ) -> str:
        """Build (but do not execute) the full CREATE OR REPLACE TABLE
        statement. Split out from ``load`` so the generated SQL can be
        unit-tested without touching BigQuery.

        ``table_name`` is an optional override for the derived Stage 3
        name (``prototype_table_name(year, month)``). Stage 4's general
        monthly CLI passes its own ``citibike_weather_monthly_YYYY_MM``
        name here; when omitted, behavior is unchanged from Stage 3.
        """
        # Validate every table reference before any of them is ever
        # interpolated into SQL text -- source tables and destination alike.
        validate_table_id(citibike_table)
        validate_table_id(weather_table)

        resolved_table_name = table_name if table_name is not None else prototype_table_name(year, month)
        destination_table_id = f"{destination_project}.{destination_dataset}.{resolved_table_name}"
        destination_ref = validate_table_id(destination_table_id)
        qualified_destination = (
            f"{destination_ref.project}.{destination_ref.dataset_id}.{destination_ref.table_id}"
        )

        select_sql = build_prototype_query(citibike_table, weather_table)
        return f"CREATE OR REPLACE TABLE `{qualified_destination}` AS\n{select_sql}"

    def load(
        self,
        *,
        destination_project: str,
        destination_dataset: str,
        year: int,
        month: int,
        citibike_table: str,
        weather_table: str,
        start_date: date,
        end_date: date,
        table_name: Optional[str] = None,
    ) -> bigquery.TableReference:
        """Execute the CTAS load for the given month and return the
        destination table reference.

        ``table_name`` is an optional override -- see ``build_load_ddl``.
        """
        validate_table_id(citibike_table)
        validate_table_id(weather_table)

        resolved_table_name = table_name if table_name is not None else prototype_table_name(year, month)
        destination_table_id = f"{destination_project}.{destination_dataset}.{resolved_table_name}"
        destination_ref = validate_table_id(destination_table_id)

        ddl_sql = self.build_load_ddl(
            destination_project=destination_project,
            destination_dataset=destination_dataset,
            year=year,
            month=month,
            citibike_table=citibike_table,
            weather_table=weather_table,
            table_name=table_name,
        )

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("start_date", "DATE", start_date),
                bigquery.ScalarQueryParameter("end_date", "DATE", end_date),
            ]
        )
        query_job = self._client.query(ddl_sql, job_config=job_config, location=self.location)
        query_job.result()  # block until the CTAS completes
        return destination_ref
