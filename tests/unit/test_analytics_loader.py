"""Unit tests for src/loading/analytics_loader.py -- no network access."""
import pytest

from src.loading.analytics_loader import AnalyticsLoader

MONTHLY_IDS = [
    "proj.ds.citibike_weather_monthly_2025_01",
    "proj.ds.citibike_weather_monthly_2025_02",
]


class FakeQueryJob:
    def __init__(self):
        self.result_called = False

    def result(self):
        self.result_called = True
        return []


class FakeClient:
    def __init__(self, raise_exc=None):
        self.raise_exc = raise_exc
        self.calls = []
        self.job = FakeQueryJob()

    def query(self, sql, location=None):
        self.calls.append({"sql": sql, "location": location})
        if self.raise_exc:
            raise self.raise_exc
        return self.job


class TestBuildLoadDdl:
    def test_wraps_analytics_select_in_create_or_replace(self):
        loader = AnalyticsLoader(project="billing", client=FakeClient())
        ddl = loader.build_load_ddl(
            destination_project="dp",
            destination_dataset="dd",
            monthly_table_ids=MONTHLY_IDS,
        )
        assert ddl.startswith(
            "CREATE OR REPLACE TABLE `dp.dd.citibike_weather_analytics` AS\n"
        )
        assert "WITH combined AS (" in ddl
        assert "UNION ALL" in ddl
        assert "ORDER BY date" in ddl

    def test_default_table_name_is_analytics(self):
        loader = AnalyticsLoader(project="billing", client=FakeClient())
        ddl = loader.build_load_ddl(
            destination_project="dp", destination_dataset="dd", monthly_table_ids=MONTHLY_IDS[:1]
        )
        assert "citibike_weather_analytics" in ddl

    def test_invalid_source_id_raises(self):
        loader = AnalyticsLoader(project="billing", client=FakeClient())
        with pytest.raises(ValueError):
            loader.build_load_ddl(
                destination_project="dp",
                destination_dataset="dd",
                monthly_table_ids=["not-a-valid-id"],
            )

    def test_invalid_destination_dataset_raises(self):
        loader = AnalyticsLoader(project="billing", client=FakeClient())
        with pytest.raises(ValueError):
            loader.build_load_ddl(
                destination_project="dp",
                destination_dataset="bad-dataset-with-hyphens",
                monthly_table_ids=MONTHLY_IDS[:1],
            )


class TestLoad:
    def test_executes_and_returns_ref(self):
        client = FakeClient()
        loader = AnalyticsLoader(project="billing", client=client)
        ref = loader.load(
            destination_project="dp", destination_dataset="dd", monthly_table_ids=MONTHLY_IDS
        )
        assert client.job.result_called is True
        assert len(client.calls) == 1
        assert client.calls[0]["sql"].startswith("CREATE OR REPLACE TABLE")
        assert ref.project == "dp"
        assert ref.dataset_id == "dd"
        assert ref.table_id == "citibike_weather_analytics"

    def test_load_error_propagates(self):
        client = FakeClient(raise_exc=RuntimeError("boom"))
        loader = AnalyticsLoader(project="billing", client=client)
        with pytest.raises(RuntimeError):
            loader.load(
                destination_project="dp", destination_dataset="dd", monthly_table_ids=MONTHLY_IDS
            )
