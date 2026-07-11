import inspect
from datetime import date

import pytest

import src.pipeline.monthly_pipeline as monthly_pipeline
from src.extraction.config import Config
from src.pipeline.batch_pipeline import EXIT_INVALID_RANGE, EXIT_LOGGING_FAILURE, execute_batch
from src.pipeline.monthly_pipeline import (
    EXIT_AUTH_OR_QUERY_ERROR,
    EXIT_LOAD_ERROR,
    EXIT_SUCCESS,
    EXIT_VALIDATION_FAILURE,
)

CITIBIKE_STATS = {"min_date": date(2013, 6, 1), "max_date": date(2026, 5, 31)}
WEATHER_STATS = {"min_date": date(1876, 1, 1), "max_date": date(2026, 5, 29)}


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


class FakeLogger:
    """In-memory stand-in for JsonlBatchLogger's two-method interface."""

    def __init__(self):
        self.month_runs = []
        self.summaries = []

    def log_month_run(self, **fields):
        self.month_runs.append(fields)

    def log_summary(self, **fields):
        self.summaries.append(fields)

    @property
    def skipped(self):
        return [m for m in self.month_runs if m["status"] == "skipped"]

    @property
    def attempted(self):
        return [m for m in self.month_runs if m["status"] != "skipped"]


class FailingLogger:
    """Raises on a chosen method to simulate a broken run log (disk
    full, permission revoked, etc.) -- proves execute_batch maps any
    log-write failure to exit code 8.
    """

    def __init__(self, fail_on):
        self.fail_on = fail_on
        self.month_runs = []
        self.summaries = []

    def log_month_run(self, **fields):
        if self.fail_on == "log_month_run":
            raise OSError("simulated disk-full error writing run log")
        self.month_runs.append(fields)

    def log_summary(self, **fields):
        if self.fail_on == "log_summary":
            raise OSError("simulated disk-full error writing run log")
        self.summaries.append(fields)


def make_execute_month(results_by_month=None, default=EXIT_SUCCESS, calls=None, kwargs_seen=None, bytes_by_month=None):
    results_by_month = results_by_month or {}
    bytes_by_month = bytes_by_month or {}

    def _execute_month(*, year, month, table_name, print_fn=print, **kwargs):
        if calls is not None:
            calls.append((year, month, table_name))
        if kwargs_seen is not None:
            kwargs_seen.append(
                {"year": year, "month": month, "table_name": table_name, "print_fn": print_fn, **kwargs}
            )
        if (year, month) in bytes_by_month:
            print_fn(f"[DRY RUN] estimated bytes processed: {bytes_by_month[(year, month)]}")
        return results_by_month.get((year, month), default)

    return _execute_month


def base_kwargs(**overrides):
    kwargs = dict(
        start_year=2025,
        start_month=1,
        end_year=2025,
        end_month=3,
        dry_run=False,
        validate_only=False,
        continue_on_error=False,
        config=make_config(),
        destination_project="my-billing-project",
        destination_dataset="my_dataset",
        read_client=FakeReadClient(),
        query_client=object(),  # execute_batch never calls this directly; only forwarded
        loader=object(),  # ditto -- forwarded to execute_month, which is faked in these tests
        logger=FakeLogger(),
        print_fn=lambda *a: None,
    )
    kwargs.update(overrides)
    return kwargs


class TestReusesStage4:
    def test_default_execute_month_is_the_real_stage4_execute(self):
        sig = inspect.signature(execute_batch)
        assert sig.parameters["execute_month"].default is monthly_pipeline.execute


class TestPreflight:
    def test_source_range_failure_returns_auth_query_error(self):
        kwargs = base_kwargs(read_client=FakeReadClient(raise_exc=RuntimeError("permission denied")))
        result = execute_batch(**kwargs, execute_month=make_execute_month())
        assert result == EXIT_AUTH_OR_QUERY_ERROR

    def test_source_range_failure_never_processes_any_month(self):
        calls = []
        kwargs = base_kwargs(read_client=FakeReadClient(raise_exc=RuntimeError("boom")))
        execute_batch(**kwargs, execute_month=make_execute_month(calls=calls))
        assert calls == []

    def test_invalid_unavailable_range_returns_4(self):
        # EXIT_INVALID_RANGE is Stage 4's EXIT_INVALID_MONTH reused (4),
        # not a batch-specific code.
        assert EXIT_INVALID_RANGE == 4
        kwargs = base_kwargs(
            read_client=FakeReadClient(
                weather_stats={"min_date": date(1876, 1, 1), "max_date": date(2025, 2, 15)}
            ),
        )
        result = execute_batch(**kwargs, execute_month=make_execute_month())
        assert result == EXIT_INVALID_RANGE
        assert result == 4

    def test_preflight_rejection_attempts_zero_months(self):
        calls = []
        kwargs = base_kwargs(
            read_client=FakeReadClient(
                weather_stats={"min_date": date(1876, 1, 1), "max_date": date(2025, 2, 15)}
            ),
        )
        execute_batch(**kwargs, execute_month=make_execute_month(calls=calls))
        assert calls == []

    def test_preflight_failure_logs_every_requested_month_as_skipped_month_run(self):
        logger = FakeLogger()
        kwargs = base_kwargs(
            read_client=FakeReadClient(
                weather_stats={"min_date": date(1876, 1, 1), "max_date": date(2025, 2, 15)}
            ),
            logger=logger,
        )
        execute_batch(**kwargs, execute_month=make_execute_month())
        assert len(logger.month_runs) == 3  # Jan, Feb, Mar all get a month_run record
        assert len(logger.skipped) == 3
        assert all(m["reason"] == "preflight_failed" for m in logger.skipped)
        assert all(m["exit_code"] is None for m in logger.skipped)
        assert len(logger.summaries) == 1
        assert logger.summaries[0]["exit_code"] == EXIT_INVALID_RANGE
        assert logger.summaries[0]["outcome"] == "preflight_failed"


class TestLoggingFailure:
    def test_month_run_write_failure_returns_8(self):
        logger = FailingLogger(fail_on="log_month_run")
        kwargs = base_kwargs(logger=logger)
        result = execute_batch(**kwargs, execute_month=make_execute_month())
        assert result == EXIT_LOGGING_FAILURE
        assert result == 8

    def test_summary_write_failure_returns_8_even_when_all_months_succeeded(self):
        logger = FailingLogger(fail_on="log_summary")
        kwargs = base_kwargs(logger=logger)
        result = execute_batch(**kwargs, execute_month=make_execute_month())
        assert result == EXIT_LOGGING_FAILURE

    def test_month_run_write_failure_during_preflight_skip_logging_returns_8(self):
        logger = FailingLogger(fail_on="log_month_run")
        kwargs = base_kwargs(
            read_client=FakeReadClient(
                weather_stats={"min_date": date(1876, 1, 1), "max_date": date(2025, 2, 15)}
            ),
            logger=logger,
        )
        result = execute_batch(**kwargs, execute_month=make_execute_month())
        assert result == EXIT_LOGGING_FAILURE

    def test_logging_failure_stops_further_processing(self):
        # log_month_run fails on the very first month -- the second and
        # third months must never be attempted once the run log is
        # known to be broken.
        logger = FailingLogger(fail_on="log_month_run")
        calls = []
        kwargs = base_kwargs(logger=logger)
        execute_batch(**kwargs, execute_month=make_execute_month(calls=calls))
        assert calls == [(2025, 1, "citibike_weather_monthly_2025_01")]


class TestStopOnFirstFailureDefault:
    def test_stops_after_first_failure_skips_remaining(self):
        calls = []
        logger = FakeLogger()
        results = {(2025, 2): EXIT_LOAD_ERROR}
        kwargs = base_kwargs(logger=logger)
        result = execute_batch(**kwargs, execute_month=make_execute_month(results_by_month=results, calls=calls))

        assert result == EXIT_LOAD_ERROR
        assert calls == [
            (2025, 1, "citibike_weather_monthly_2025_01"),
            (2025, 2, "citibike_weather_monthly_2025_02"),
        ]
        assert len(logger.attempted) == 2
        assert len(logger.skipped) == 1
        assert logger.skipped[0] == {
            "year": 2025,
            "month": 3,
            "table_name": "citibike_weather_monthly_2025_03",
            "status": "skipped",
            "exit_code": None,
            "reason": "stopped_after_failure",
        }

    def test_all_success_returns_0(self):
        result = execute_batch(**base_kwargs(), execute_month=make_execute_month())
        assert result == EXIT_SUCCESS

    def test_summary_reflects_stopped_early(self):
        logger = FakeLogger()
        results = {(2025, 1): EXIT_LOAD_ERROR}
        execute_batch(**base_kwargs(logger=logger), execute_month=make_execute_month(results_by_month=results))
        assert logger.summaries[0]["stopped_early"] is True


class TestContinueOnError:
    def test_processes_every_month_despite_failures(self):
        calls = []
        results = {(2025, 1): EXIT_VALIDATION_FAILURE, (2025, 2): EXIT_LOAD_ERROR}
        kwargs = base_kwargs(continue_on_error=True)
        execute_batch(**kwargs, execute_month=make_execute_month(results_by_month=results, calls=calls))
        assert len(calls) == 3

    def test_returns_first_failed_months_exit_code_chronologically(self):
        # Month 1 fails with VALIDATION_FAILURE (7), month 2 fails with
        # LOAD_ERROR (6). Chronologically month 1 comes first, so its
        # code must win -- regardless of severity, insertion order into
        # the results dict, or which failure "sounds worse".
        results = {(2025, 1): EXIT_VALIDATION_FAILURE, (2025, 2): EXIT_LOAD_ERROR}
        kwargs = base_kwargs(continue_on_error=True)
        result = execute_batch(**kwargs, execute_month=make_execute_month(results_by_month=results))
        assert result == EXIT_VALIDATION_FAILURE

    def test_returns_first_failed_months_exit_code_even_when_later_month_defined_first_in_dict(self):
        # Same as above but with the dict insertion order reversed --
        # proves the result depends on chronological (year, month)
        # order, not dict/iteration order.
        results = {(2025, 3): EXIT_LOAD_ERROR, (2025, 2): EXIT_VALIDATION_FAILURE}
        kwargs = base_kwargs(continue_on_error=True)
        result = execute_batch(**kwargs, execute_month=make_execute_month(results_by_month=results))
        assert result == EXIT_VALIDATION_FAILURE  # 2025-02 precedes 2025-03

    def test_no_months_skipped_when_continuing(self):
        logger = FakeLogger()
        results = {(2025, 1): EXIT_LOAD_ERROR}
        kwargs = base_kwargs(continue_on_error=True, logger=logger)
        execute_batch(**kwargs, execute_month=make_execute_month(results_by_month=results))
        assert logger.skipped == []

    def test_summary_stopped_early_is_false(self):
        logger = FakeLogger()
        results = {(2025, 1): EXIT_LOAD_ERROR}
        execute_batch(
            **base_kwargs(continue_on_error=True, logger=logger),
            execute_month=make_execute_month(results_by_month=results),
        )
        assert logger.summaries[0]["stopped_early"] is False


class TestModesPassThrough:
    def test_dry_run_flag_forwarded_to_each_month(self):
        seen = []
        kwargs = base_kwargs(dry_run=True, end_month=1)
        execute_batch(**kwargs, execute_month=make_execute_month(kwargs_seen=seen))
        assert len(seen) == 1
        assert seen[0]["dry_run"] is True
        assert seen[0]["validate_only"] is False

    def test_validate_only_flag_forwarded_to_each_month(self):
        seen = []
        kwargs = base_kwargs(validate_only=True, end_month=1)
        execute_batch(**kwargs, execute_month=make_execute_month(kwargs_seen=seen))
        assert len(seen) == 1
        assert seen[0]["validate_only"] is True
        assert seen[0]["dry_run"] is False

    def test_destination_project_and_dataset_forwarded(self):
        seen = []
        kwargs = base_kwargs(end_month=1, destination_project="proj-x", destination_dataset="dataset-y")
        execute_batch(**kwargs, execute_month=make_execute_month(kwargs_seen=seen))
        assert seen[0]["destination_project"] == "proj-x"
        assert seen[0]["destination_dataset"] == "dataset-y"


class TestLogging:
    def test_skipped_months_receive_month_run_records(self):
        logger = FakeLogger()
        results = {(2025, 2): EXIT_LOAD_ERROR}
        execute_batch(**base_kwargs(logger=logger), execute_month=make_execute_month(results_by_month=results))
        # March is skipped (stop-on-first-failure default) -- it must
        # still produce a "month_run" record, just with status="skipped".
        skipped_march = [m for m in logger.month_runs if m["month"] == 3]
        assert len(skipped_march) == 1
        assert skipped_march[0]["status"] == "skipped"

    def test_logs_one_month_run_record_per_attempted_month(self):
        logger = FakeLogger()
        execute_batch(**base_kwargs(logger=logger), execute_month=make_execute_month())
        assert len(logger.month_runs) == 3
        assert all(m["status"] == "success" for m in logger.month_runs)
        assert all(m["exit_code"] == EXIT_SUCCESS for m in logger.month_runs)

    def test_summary_counts_are_accurate(self):
        logger = FakeLogger()
        results = {(2025, 2): EXIT_LOAD_ERROR}
        execute_batch(**base_kwargs(logger=logger), execute_month=make_execute_month(results_by_month=results))
        summary = logger.summaries[0]
        assert summary["requested_months"] == 3
        assert summary["succeeded"] == 1
        assert summary["failed"] == 1
        assert summary["skipped"] == 1

    def test_exactly_one_final_batch_summary_record_is_written(self):
        logger = FakeLogger()
        execute_batch(**base_kwargs(logger=logger), execute_month=make_execute_month())
        assert len(logger.summaries) == 1

    def test_exactly_one_batch_summary_record_when_continuing_on_error(self):
        logger = FakeLogger()
        results = {(2025, 1): EXIT_LOAD_ERROR, (2025, 2): EXIT_VALIDATION_FAILURE}
        execute_batch(
            **base_kwargs(logger=logger, continue_on_error=True),
            execute_month=make_execute_month(results_by_month=results),
        )
        assert len(logger.summaries) == 1

    def test_summary_mode_label_reflects_dry_run(self):
        logger = FakeLogger()
        execute_batch(
            **base_kwargs(logger=logger, dry_run=True, end_month=1),
            execute_month=make_execute_month(),
        )
        assert logger.summaries[0]["mode"] == "dry-run"


class TestTotalEstimatedBytes:
    def test_null_outside_dry_run_mode_normal(self):
        logger = FakeLogger()
        execute_batch(
            **base_kwargs(logger=logger, dry_run=False, validate_only=False),
            execute_month=make_execute_month(),
        )
        assert logger.summaries[0]["total_estimated_bytes"] is None

    def test_null_outside_dry_run_mode_validate_only(self):
        logger = FakeLogger()
        execute_batch(
            **base_kwargs(logger=logger, dry_run=False, validate_only=True),
            execute_month=make_execute_month(),
        )
        assert logger.summaries[0]["total_estimated_bytes"] is None

    def test_null_outside_dry_run_mode_even_on_preflight_failure(self):
        logger = FakeLogger()
        kwargs = base_kwargs(
            logger=logger,
            dry_run=False,
            read_client=FakeReadClient(
                weather_stats={"min_date": date(1876, 1, 1), "max_date": date(2025, 2, 15)}
            ),
        )
        execute_batch(**kwargs, execute_month=make_execute_month())
        assert logger.summaries[0]["total_estimated_bytes"] is None

    def test_populated_and_summed_across_months_in_dry_run_mode(self):
        logger = FakeLogger()
        bytes_by_month = {(2025, 1): 1000, (2025, 2): 2000, (2025, 3): 500}
        execute_batch(
            **base_kwargs(logger=logger, dry_run=True),
            execute_month=make_execute_month(bytes_by_month=bytes_by_month),
        )
        assert logger.summaries[0]["total_estimated_bytes"] == 3500

    def test_zero_when_dry_run_but_preflight_failed(self):
        logger = FakeLogger()
        kwargs = base_kwargs(
            logger=logger,
            dry_run=True,
            read_client=FakeReadClient(
                weather_stats={"min_date": date(1876, 1, 1), "max_date": date(2025, 2, 15)}
            ),
        )
        execute_batch(**kwargs, execute_month=make_execute_month())
        assert logger.summaries[0]["total_estimated_bytes"] == 0
