"""Loads the Stage 6 dashboard-ready analytics table into the caller's
own BigQuery destination project/dataset.

A thin sibling of ``src.loading.prototype_loader.PrototypeLoader`` -- it
reuses the SAME controls and the SAME idempotent-load pattern, but for a
parameterless multi-table ``UNION ALL`` CTAS rather than the month/date-
parameterized prototype join. ``PrototypeLoader`` is left completely
untouched (no redesign of the committed Stage 3-5 loader); the two
coexist. See ``DECISIONS.md`` D-027 for why this is a new loader rather
than a change to ``PrototypeLoader``.

Controls preserved from the prototype loader:
  - Destination project and dataset are always explicit arguments --
    never hardcoded, never inferred silently.
  - The destination dataset is NEVER auto-created. If it doesn't exist,
    the ``CREATE OR REPLACE TABLE`` fails with BigQuery's own "not found"
    error rather than this code creating one.
  - The destination table name defaults to the single fixed Stage 6 name
    (``citibike_weather_analytics``), not a user-supplied value.
  - Idempotent: ``CREATE OR REPLACE TABLE ... AS SELECT`` fully replaces
    the table in one atomic statement; re-running never appends.
  - Every source (monthly) table id AND the destination id is validated
    with ``validate_table_id`` before being interpolated into SQL.
  - Authenticates via Application Default Credentials only -- no
    service-account key file is read or referenced.

There are no scalar query parameters here: the analytics CTAS selects
whole monthly tables (no date-range predicate), so unlike the prototype
loader it binds no ``@start_date``/``@end_date``.
"""
from __future__ import annotations

from typing import List, Optional

from google.cloud import bigquery

from src.analytics.analytics_query import analytics_table_name, build_analytics_select
from src.extraction.table_id import validate_table_id


class AnalyticsLoader:
    """Wraps a ``google.cloud.bigquery.Client`` for the single write
    Stage 6 performs: the analytics CTAS load.

    ``client`` can be injected (e.g. a fake) for testing without any
    network access, matching ``BigQueryReadOnlyClient`` / ``PrototypeLoader``.
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
        monthly_table_ids: List[str],
        table_name: Optional[str] = None,
    ) -> str:
        """Build (but do not execute) the full ``CREATE OR REPLACE TABLE``
        statement. Split out from ``load`` so the generated SQL can be
        unit-tested without touching BigQuery.

        Every ``monthly_table_ids`` entry and the destination id are
        validated here before interpolation. ``table_name`` defaults to
        ``analytics_table_name()`` (the fixed Stage 6 name).
        """
        for source_id in monthly_table_ids:
            validate_table_id(source_id)

        resolved_table_name = table_name if table_name is not None else analytics_table_name()
        destination_table_id = f"{destination_project}.{destination_dataset}.{resolved_table_name}"
        destination_ref = validate_table_id(destination_table_id)
        qualified_destination = (
            f"{destination_ref.project}.{destination_ref.dataset_id}.{destination_ref.table_id}"
        )

        select_sql = build_analytics_select(monthly_table_ids)
        return f"CREATE OR REPLACE TABLE `{qualified_destination}` AS\n{select_sql}"

    def load(
        self,
        *,
        destination_project: str,
        destination_dataset: str,
        monthly_table_ids: List[str],
        table_name: Optional[str] = None,
    ) -> bigquery.TableReference:
        """Execute the analytics CTAS load and return the destination
        table reference."""
        resolved_table_name = table_name if table_name is not None else analytics_table_name()
        destination_table_id = f"{destination_project}.{destination_dataset}.{resolved_table_name}"
        destination_ref = validate_table_id(destination_table_id)

        ddl_sql = self.build_load_ddl(
            destination_project=destination_project,
            destination_dataset=destination_dataset,
            monthly_table_ids=monthly_table_ids,
            table_name=table_name,
        )

        query_job = self._client.query(ddl_sql, location=self.location)
        query_job.result()  # block until the CTAS completes
        return destination_ref
