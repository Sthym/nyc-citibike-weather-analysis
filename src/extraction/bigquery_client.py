"""Thin, read-only BigQuery client wrapper.

Authenticates exclusively via Application Default Credentials -- run
``gcloud auth application-default login`` locally before using this. No
service-account key file is read, referenced, or supported here.

Only metadata reads (row count) and a single-column aggregate query
(date-range stats) are performed. No full-table reads, no
transformations, no writes, no destination tables.
"""
from __future__ import annotations

from typing import Optional, TypedDict

from google.cloud import bigquery

from .table_id import validate_table_id


class DateRangeStats(TypedDict):
    distinct_dates: int
    null_dates: int
    min_date: object  # datetime.date
    max_date: object  # datetime.date


class BigQueryReadOnlyClient:
    """Wraps a ``google.cloud.bigquery.Client`` for read-only metadata checks.

    ``project`` is the caller's own billing/query-execution project --
    distinct from the project(s) named in the source table IDs being
    queried. ``client`` can be injected (e.g. a fake/mock) for testing
    without any network access.
    """

    def __init__(
        self,
        project: str,
        location: str = "US",
        client: Optional[bigquery.Client] = None,
    ):
        self.project = project
        self.location = location
        # Application Default Credentials are used automatically when no
        # explicit credentials are passed to the SDK client.
        self._client = client or bigquery.Client(project=project)

    def get_table_row_count(self, table_id: str) -> int:
        """Return the table's row count via metadata only (no query job)."""
        table_ref = validate_table_id(table_id)
        table = self._client.get_table(table_ref)
        return table.num_rows

    def get_date_range_stats(self, table_id: str) -> DateRangeStats:
        """Run a read-only aggregate query over the ``date`` column.

        Scans only the ``date`` column for this table -- not a
        full-table download. Returns distinct-date count, null-date
        count, and the min/max date.
        """
        table_ref = validate_table_id(table_id)
        qualified = f"{table_ref.project}.{table_ref.dataset_id}.{table_ref.table_id}"

        sql = (
            "SELECT\n"
            "  COUNT(DISTINCT date) AS distinct_dates,\n"
            "  COUNTIF(date IS NULL) AS null_dates,\n"
            "  MIN(date) AS min_date,\n"
            "  MAX(date) AS max_date\n"
            f"FROM `{qualified}`"
        )

        query_job = self._client.query(sql, location=self.location)
        rows = list(query_job.result())
        row = rows[0]
        return {
            "distinct_dates": row["distinct_dates"],
            "null_dates": row["null_dates"],
            "min_date": row["min_date"],
            "max_date": row["max_date"],
        }
