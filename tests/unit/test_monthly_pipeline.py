from datetime import date

import pytest

from src.extraction.config import Config
from src.transformation.prototype_validator import ADDITIVE_CITIBIKE_COLUMNS
from src.pipeline.monthly_pipeline import (
    EXIT_AUTH_OR_QUERY_ERROR,
    EXIT_CONFIG_ERROR,
    EXIT_INVALID_MONTH,
    EXIT_LOAD_ERROR,
    EXIT_SUCCESS,
    EXIT_VALIDATION_FAILURE,
    execute,
)

D1 = date(2025, 2, 1)

CITIBIKE_STATS = {
    "distinct_dates": 4738,
    "null_dates": 0,
    "min_date": date(2013, 6, 1),
    "max_date": date(2026, 5, 31),
}
WEATHER_STATS = {
    "distinct_dates": 54912,
    "null_dates": 0,
    "min_date": date(1876, 1, 1),
    "max_date": date(2026, 5, 29),
}


def make_config():
    return Config(
        gcp_project_id="my-billing-project",
        citibike_table="nyu-datasets.citibike.m_daily_trips",
        weather_table="nyu-datasets.weather.m_weather_daily_nyc",
        bq_location="US",
    )


class FakeReadClient:
    def __init__(self, citibike_stats=None, weather_stats=None, raise_exc=None):
        self.citibike_stats = citibike_stats or CITIBIKE_STATS
        self.weather_stats = weather_stats or WEATHER_STATS
        self.raise_exc = raise_exc
        self.calls = []

    def get_date_range_stats(self, table_id):
        self.calls.append(table_id)
        if self.raise_exc:
            raise self.raise_exc
        if "citibike" in table_id:
            return self.citibike_stats
        return self.weather_stats


class FakeQueryJob:
    def __init__(self, rows=None, total_bytes_processed=None):
        self._rows = rows or []
        self.total_bytes_processed = total_bytes_processed

    def result(self):
        return self._rows


class FakeQueryClient:
    """Dispatches based on distinguishing markers in the SQL text --
    mirrors the small set of query shapes monthly_pipeline.py actually
    generates (structural, additive sums x2, row count, three per-date
    row selects, plus a dry-run estimate).
    """

    def __init__(self, dispatcher=None, raise_exc=None):
        self.dispatcher = dispatcher
        self.raise_exc = raise_exc
        self.calls = []

    def query(self, sql, job_config=None, location=None):
        self.calls.append({"sql": sql, "job_config": job_config, "location": location})
        if self.raise_exc:
            raise self.raise_exc
        if job_config is not None and getattr(job_config, "dry_run", False):
            return FakeQueryJob(total_bytes_processed=123456)
        return self.dispatcher(sql)


def happy_path_dispatcher(sql):
    has_where = "WHERE date BETWEEN" in sql
    if "COUNT(*) AS row_count" in sql and not has_where:
        return FakeQueryJob(
            [
                {
                    "row_count": 1,
                    "distinct_dates": 1,
                    "null_dates": 0,
                    "min_date": D1,
                    "max_date": D1,
                    "matched": 1,
                    "unmatched": 0,
                    "null_flag": 0,
                }
            ]
        )
    if "COUNT(*) AS row_count" in sql and has_where:
        return FakeQueryJob([{"row_count": 1}])
    if "SUM(" in sql and not has_where:
        return FakeQueryJob([{col: 10 for col in ADDITIVE_CITIBIKE_COLUMNS}])
    if "SUM(" in sql and has_where:
        return FakeQueryJob([{col: 10 for col in ADDITIVE_CITIBIKE_COLUMNS}])
    if "weather_matched" in sql and not has_where:
        return FakeQueryJob(
            [
                {
                    "date": D1,
                    "avg_trip_duration_minutes": 15.0,
                    "median_trip_duration_minutes": 12.0,
                    "avg_distance_meters": 2000.0,
                    "weather_matched": True,
                    "tmin_f": 30.0,
                    "tmax_f": 40.0,
                    "tavg_f": 35.0,
                    "prcp_inches": 0.1,
                    "is_rainy": True,
                    "snow_inches": 0.0,
                    "is_snowy": False,
                    "season": "Winter",
                }
            ]
        )
    if "num_member_trips" in sql and has_where:
        return FakeQueryJob(
            [
                {
                    "date": D1,
                    "avg_trip_duration_minutes": 15.0,
                    "median_trip_duration_minutes": 12.0,
                    "avg_distance_meters": 2000.0,
                    "num_member_trips": 80,
                    "num_casual_trips": 20,
                    "num_nyc_trips": 90,
                    "num_jc_trips": 10,
                    "num_trips": 100,
                }
            ]
        )
    if "is_rainy" in sql and has_where and "num_member_trips" not in sql:
        return FakeQueryJob(
            [
                {
                    "date": D1,
                    "tmin_f": 30.0,
                    "tmax_f": 40.0,
                    "tavg_f": 35.0,
                    "prcp_inches": 0.1,
                    "snow_inches": 0.0,
                    "is_rainy": 1,
                    "is_snowy": 0,
                    "season": "Winter",
                }
            ]
        )
    raise AssertionError(f"unexpected SQL in test dispatcher:\n{sql}")


class FakeLoader:
    def __init__(self, raise_exc=None):
        self.raise_exc = raise_exc
        self.load_calls = []

    def load(self, **kwargs):
        self.load_calls.append(kwargs)
        if self.raise_exc:
            raise self.raise_exc


def base_kwargs(**overrides):
    kwargs = dict(
        year=2025,
        month=2,
        table_name="citibike_weather_monthly_2025_02",
        dry_run=False,
        validate_only=False,
        config=make_config(),
        destination_project="my-billing-project",
        destination_dataset="my_dataset",
        read_client=FakeReadClient(),
        query_client=FakeQueryClient(dispatcher=happy_path_dispatcher),
        loader=FakeLoader(),
        print_fn=lambda *a: None,
    )
    kwargs.update(overrides)
    return kwargs


class TestConfigError:
    def test_invalid_destination_table_id_returns_config_error(self):
        kwargs = base_kwargs(destination_dataset="bad dataset name")
        assert execute(**kwargs) == EXIT_CONFIG_ERROR

    def test_config_error_never_touches_read_client(self):
        read_client = FakeReadClient()
        kwargs = base_kwargs(destination_dataset="bad dataset name", read_client=read_client)
        execute(**kwargs)
        assert read_client.calls == []


class TestSourceRangeRetrieval:
    def test_failure_returns_auth_query_error(self):
        kwargs = base_kwargs(read_client=FakeReadClient(raise_exc=RuntimeError("permission denied")))
        assert execute(**kwargs) == EXIT_AUTH_OR_QUERY_ERROR


class TestMonthValidation:
    def test_month_outside_effective_range_returns_invalid_month(self):
        kwargs = base_kwargs(year=2030, month=1)
        assert execute(**kwargs) == EXIT_INVALID_MONTH

    def test_invalid_month_never_calls_loader_or_query_client(self):
        loader = FakeLoader()
        query_client = FakeQueryClient(dispatcher=happy_path_dispatcher)
        kwargs = base_kwargs(year=2030, month=1, loader=loader, query_client=query_client)
        execute(**kwargs)
        assert loader.load_calls == []
        assert query_client.calls == []

    def test_partial_month_at_effective_boundary_rejected(self):
        # weather max_date is 2026-05-29 -- May 2026 only partially overlaps.
        kwargs = base_kwargs(year=2026, month=5)
        assert execute(**kwargs) == EXIT_INVALID_MONTH


class TestDryRun:
    def test_success_returns_0_reports_estimate_never_loads(self):
        loader = FakeLoader()
        printed = []
        kwargs = base_kwargs(dry_run=True, loader=loader, print_fn=printed.append)
        assert execute(**kwargs) == EXIT_SUCCESS
        assert loader.load_calls == []
        assert any("bytes processed" in line for line in printed)

    def test_failure_returns_auth_query_error_never_success(self):
        query_client = FakeQueryClient(dispatcher=happy_path_dispatcher, raise_exc=RuntimeError("no dry-run perms"))
        kwargs = base_kwargs(dry_run=True, query_client=query_client)
        assert execute(**kwargs) == EXIT_AUTH_OR_QUERY_ERROR


class TestValidateOnly:
    def test_never_calls_loader(self):
        loader = FakeLoader()
        kwargs = base_kwargs(validate_only=True, loader=loader)
        execute(**kwargs)
        assert loader.load_calls == []

    def test_success_returns_0(self):
        kwargs = base_kwargs(validate_only=True)
        assert execute(**kwargs) == EXIT_SUCCESS

    def test_missing_destination_table_returns_auth_query_error(self):
        query_client = FakeQueryClient(dispatcher=happy_path_dispatcher, raise_exc=RuntimeError("404 not found"))
        kwargs = base_kwargs(validate_only=True, query_client=query_client)
        assert execute(**kwargs) == EXIT_AUTH_OR_QUERY_ERROR

    def test_validation_mismatch_returns_7(self):
        # Simplest reliable way to force a validation failure: make the
        # destination additive sum disagree with the source additive sum.
        def sum_mismatch_dispatcher(sql):
            has_where = "WHERE date BETWEEN" in sql
            if "SUM(" in sql and not has_where:
                return FakeQueryJob([{col: 999 for col in ADDITIVE_CITIBIKE_COLUMNS}])
            return happy_path_dispatcher(sql)

        kwargs = base_kwargs(validate_only=True, query_client=FakeQueryClient(dispatcher=sum_mismatch_dispatcher))
        assert execute(**kwargs) == EXIT_VALIDATION_FAILURE


class TestFullRun:
    def test_load_failure_returns_6(self):
        loader = FakeLoader(raise_exc=RuntimeError("dataset not found"))
        kwargs = base_kwargs(loader=loader)
        assert execute(**kwargs) == EXIT_LOAD_ERROR

    def test_load_failure_never_attempts_validation_read(self):
        loader = FakeLoader(raise_exc=RuntimeError("dataset not found"))
        query_client = FakeQueryClient(dispatcher=happy_path_dispatcher)
        kwargs = base_kwargs(loader=loader, query_client=query_client)
        execute(**kwargs)
        assert query_client.calls == []

    def test_success_calls_loader_exactly_once_and_returns_0(self):
        loader = FakeLoader()
        kwargs = base_kwargs(loader=loader)
        assert execute(**kwargs) == EXIT_SUCCESS
        assert len(loader.load_calls) == 1
        assert loader.load_calls[0]["table_name"] == "citibike_weather_monthly_2025_02"

    def test_validation_failure_after_successful_load_returns_7(self):
        def sum_mismatch_dispatcher(sql):
            has_where = "WHERE date BETWEEN" in sql
            if "SUM(" in sql and not has_where:
                return FakeQueryJob([{col: 999 for col in ADDITIVE_CITIBIKE_COLUMNS}])
            return happy_path_dispatcher(sql)

        loader = FakeLoader()
        kwargs = base_kwargs(loader=loader, query_client=FakeQueryClient(dispatcher=sum_mismatch_dispatcher))
        assert execute(**kwargs) == EXIT_VALIDATION_FAILURE
        assert len(loader.load_calls) == 1  # load still happened; only validation failed
