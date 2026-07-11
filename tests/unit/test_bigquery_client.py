from datetime import date
from unittest.mock import patch

import pytest

from src.extraction.bigquery_client import BigQueryReadOnlyClient


class FakeTable:
    def __init__(self, num_rows):
        self.num_rows = num_rows


class FakeQueryJob:
    def __init__(self, rows):
        self._rows = rows

    def result(self):
        return self._rows


class FakeBigQueryClient:
    """Stand-in for google.cloud.bigquery.Client -- no network involved."""

    def __init__(self):
        self.get_table_calls = []
        self.query_calls = []
        self.table_to_return = None
        self.rows_to_return = None

    def get_table(self, table_ref):
        self.get_table_calls.append(table_ref)
        return self.table_to_return

    def query(self, sql, location=None):
        self.query_calls.append({"sql": sql, "location": location})
        return FakeQueryJob(self.rows_to_return)


def _sample_row(**overrides):
    row = {
        "distinct_dates": 4738,
        "null_dates": 0,
        "min_date": date(2013, 6, 1),
        "max_date": date(2026, 5, 31),
    }
    row.update(overrides)
    return row


def test_get_table_row_count_returns_num_rows():
    fake = FakeBigQueryClient()
    fake.table_to_return = FakeTable(num_rows=4738)
    wrapper = BigQueryReadOnlyClient(project="billing-proj", client=fake)

    count = wrapper.get_table_row_count("nyu-datasets.citibike.m_daily_trips")

    assert count == 4738
    assert len(fake.get_table_calls) == 1


def test_get_date_range_stats_parses_all_four_fields():
    fake = FakeBigQueryClient()
    fake.rows_to_return = [_sample_row()]
    wrapper = BigQueryReadOnlyClient(project="billing-proj", client=fake)

    stats = wrapper.get_date_range_stats("nyu-datasets.citibike.m_daily_trips")

    assert stats == {
        "distinct_dates": 4738,
        "null_dates": 0,
        "min_date": date(2013, 6, 1),
        "max_date": date(2026, 5, 31),
    }


def test_date_range_query_includes_all_four_columns_and_date_source():
    fake = FakeBigQueryClient()
    fake.rows_to_return = [_sample_row()]
    wrapper = BigQueryReadOnlyClient(project="billing-proj", client=fake)

    wrapper.get_date_range_stats("nyu-datasets.citibike.m_daily_trips")

    sql = fake.query_calls[0]["sql"]
    assert "COUNT(DISTINCT date)" in sql
    assert "COUNTIF(date IS NULL)" in sql
    assert "MIN(date)" in sql
    assert "MAX(date)" in sql
    assert "nyu-datasets.citibike.m_daily_trips" in sql


def test_configured_location_passed_to_query():
    fake = FakeBigQueryClient()
    fake.rows_to_return = [_sample_row()]
    wrapper = BigQueryReadOnlyClient(project="billing-proj", location="EU", client=fake)

    wrapper.get_date_range_stats("nyu-datasets.citibike.m_daily_trips")

    assert fake.query_calls[0]["location"] == "EU"


def test_default_location_is_us():
    fake = FakeBigQueryClient()
    fake.rows_to_return = [_sample_row()]
    wrapper = BigQueryReadOnlyClient(project="billing-proj", client=fake)

    wrapper.get_date_range_stats("nyu-datasets.citibike.m_daily_trips")

    assert fake.query_calls[0]["location"] == "US"


def test_rejects_table_id_with_injection_before_any_query():
    fake = FakeBigQueryClient()
    wrapper = BigQueryReadOnlyClient(project="billing-proj", client=fake)

    with pytest.raises(ValueError):
        wrapper.get_date_range_stats(
            "nyu-datasets.citibike.m_daily_trips; DROP TABLE x"
        )

    assert fake.query_calls == []  # never reached the query


def test_rejects_table_id_with_injection_before_row_count():
    fake = FakeBigQueryClient()
    wrapper = BigQueryReadOnlyClient(project="billing-proj", client=fake)

    with pytest.raises(ValueError):
        wrapper.get_table_row_count("nyu-datasets.citibike.`m_daily_trips`")

    assert fake.get_table_calls == []  # never reached get_table


def test_client_constructed_with_billing_project_not_source_project():
    with patch("src.extraction.bigquery_client.bigquery.Client") as MockClient:
        BigQueryReadOnlyClient(project="my-billing-project")
        MockClient.assert_called_once_with(project="my-billing-project")
