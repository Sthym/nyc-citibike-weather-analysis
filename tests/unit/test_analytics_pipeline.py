"""Unit tests for src/analytics/analytics_pipeline.py.

Fully offline: fake discovery client (list_tables), fake query client
(dispatches on SQL text over the small set of query shapes the pipeline
generates), and a fake loader. No network access.
"""
import pytest

from src.extraction.config import Config
from src.analytics import analytics_pipeline as ap
from src.analytics.analytics_pipeline import (
    EXIT_AUTH_OR_QUERY_ERROR,
    EXIT_CONFIG_ERROR,
    EXIT_LOAD_ERROR,
    EXIT_NO_SOURCE_TABLES,
    EXIT_SUCCESS,
    EXIT_VALIDATION_FAILURE,
    execute,
)

HAPPY_AGG = {
    "row_count": 3,
    "distinct_dates": 3,
    "null_dates": 0,
    "num_trips": 100,
    "num_member_trips": 70,
    "num_casual_trips": 30,
    "prcp_inches": 1.5,
    "snow_inches": 0.0,
    "count_rainy": 1,
    "count_snowy": 0,
    "count_weather_matched": 3,
}
HAPPY_DOMAIN = {
    "bad_temperature_band": 0,
    "bad_rain_category": 0,
    "bad_snow_category": 0,
    "temp_consistency": 0,
    "rain_consistency": 0,
    "snow_consistency": 0,
}


def make_config():
    return Config(
        gcp_project_id="billing",
        citibike_table="nyu-datasets.citibike.m_daily_trips",
        weather_table="nyu-datasets.weather.m_weather_daily_nyc",
        bq_location="US",
    )


class FakeTable:
    def __init__(self, table_id):
        self.table_id = table_id


class FakeDiscoveryClient:
    def __init__(self, names, raise_exc=None):
        self._names = names
        self.raise_exc = raise_exc

    def list_tables(self, dataset_ref):
        if self.raise_exc:
            raise self.raise_exc
        return [FakeTable(n) for n in self._names]


class FakeQueryJob:
    def __init__(self, rows=None, total_bytes_processed=None):
        self._rows = rows or []
        self.total_bytes_processed = total_bytes_processed

    def result(self):
        return self._rows


class FakeQueryClient:
    def __init__(self, analytics_agg=None, source_agg=None, domain=None, raise_exc=None):
        self.analytics_agg = analytics_agg or dict(HAPPY_AGG)
        self.source_agg = source_agg or dict(HAPPY_AGG)
        self.domain = domain or dict(HAPPY_DOMAIN)
        self.raise_exc = raise_exc
        self.calls = []

    def query(self, sql, job_config=None, location=None):
        self.calls.append(sql)
        if self.raise_exc:
            raise self.raise_exc
        if job_config is not None and getattr(job_config, "dry_run", False):
            return FakeQueryJob(total_bytes_processed=987654)
        if "bad_temperature_band" in sql:
            return FakeQueryJob([self.domain])
        if "COUNT(*) AS row_count" in sql:
            if "FROM (" in sql:
                return FakeQueryJob([self.source_agg])
            return FakeQueryJob([self.analytics_agg])
        raise AssertionError(f"unexpected SQL dispatched:\n{sql}")


class FakeLoader:
    def __init__(self, raise_exc=None):
        self.raise_exc = raise_exc
        self.load_calls = []

    def load(self, **kwargs):
        self.load_calls.append(kwargs)
        if self.raise_exc:
            raise self.raise_exc
        return None


MONTHLY_NAMES = [
    "citibike_weather_monthly_2025_01",
    "citibike_weather_monthly_2025_02",
    "citibike_weather_monthly_2025_03",
]


def run(**overrides):
    kwargs = dict(
        dry_run=False,
        validate_only=False,
        config=make_config(),
        destination_project="dp",
        destination_dataset="dd",
        discovery_client=FakeDiscoveryClient(MONTHLY_NAMES),
        query_client=FakeQueryClient(),
        loader=FakeLoader(),
        print_fn=lambda *a, **k: None,
    )
    kwargs.update(overrides)
    return kwargs, execute(**kwargs)


class TestFullRun:
    def test_happy_path_returns_success_and_loads(self):
        kwargs, code = run()
        assert code == EXIT_SUCCESS
        assert len(kwargs["loader"].load_calls) == 1
        # loader received the discovered, fully-qualified, ordered ids
        assert kwargs["loader"].load_calls[0]["monthly_table_ids"] == [
            "dp.dd.citibike_weather_monthly_2025_01",
            "dp.dd.citibike_weather_monthly_2025_02",
            "dp.dd.citibike_weather_monthly_2025_03",
        ]

    def test_validation_failure_returns_7(self):
        # source row count differs from analytics -> A3 fails
        bad_source = dict(HAPPY_AGG, row_count=4)
        kwargs, code = run(query_client=FakeQueryClient(source_agg=bad_source))
        assert code == EXIT_VALIDATION_FAILURE


class TestValidateOnly:
    def test_does_not_load_but_still_validates(self):
        loader = FakeLoader()
        kwargs, code = run(validate_only=True, loader=loader)
        assert code == EXIT_SUCCESS
        assert loader.load_calls == []


class TestDryRun:
    def test_returns_success_without_loading(self):
        loader = FakeLoader()
        kwargs, code = run(dry_run=True, loader=loader)
        assert code == EXIT_SUCCESS
        assert loader.load_calls == []


class TestErrorPaths:
    def test_no_monthly_tables_returns_4(self):
        client = FakeDiscoveryClient(["citibike_weather_analytics"])
        _, code = run(discovery_client=client)
        assert code == EXIT_NO_SOURCE_TABLES

    def test_listing_failure_returns_5(self):
        client = FakeDiscoveryClient(MONTHLY_NAMES, raise_exc=RuntimeError("auth"))
        _, code = run(discovery_client=client)
        assert code == EXIT_AUTH_OR_QUERY_ERROR

    def test_load_failure_returns_6(self):
        _, code = run(loader=FakeLoader(raise_exc=RuntimeError("boom")))
        assert code == EXIT_LOAD_ERROR

    def test_gather_failure_returns_5(self):
        _, code = run(query_client=FakeQueryClient(raise_exc=RuntimeError("query")))
        assert code == EXIT_AUTH_OR_QUERY_ERROR

    def test_bad_destination_dataset_returns_config_error(self):
        # A hyphen is illegal in a dataset id -> table-id validation fails.
        _, code = run(destination_dataset="bad-dataset")
        assert code == EXIT_CONFIG_ERROR


class TestExitCodeContract:
    def test_no_source_tables_reuses_invalid_month_code(self):
        from src.pipeline.monthly_pipeline import EXIT_INVALID_MONTH

        assert EXIT_NO_SOURCE_TABLES == EXIT_INVALID_MONTH

    def test_stage6_does_not_define_a_logging_failure_code(self):
        # Exit code 8 belongs to Stage 5 logging; Stage 6 must not use or
        # redefine it.
        assert not hasattr(ap, "EXIT_LOGGING_FAILURE")
