"""CLI-layer tests for scripts/build_analytics_table.py.

Only exercises argparse-level and input-shape behavior (usage errors,
mutual exclusion, YYYY-MM parsing, and the config boundary) -- all
intercepted before any BigQuery client is constructed, so no network
access is needed. Pipeline control-flow (exit codes 0/4/5/6/7) is
covered in test_analytics_pipeline.py.
"""
import importlib.util
import os

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load_script(name, filename):
    path = os.path.join(REPO_ROOT, "scripts", filename)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def cli():
    return _load_script("build_analytics_table_under_test", "build_analytics_table.py")


class TestParseYearMonthArg:
    def test_valid(self, cli):
        assert cli.parse_year_month_arg("2025-06", "--start") == (2025, 6)

    @pytest.mark.parametrize("bad", ["2025", "2025-13", "2025-00", "nope", "2025-06-01"])
    def test_bad_shapes_raise(self, cli, bad):
        from src.pipeline.month_period import CliUsageError

        with pytest.raises(CliUsageError):
            cli.parse_year_month_arg(bad, "--start")


class TestArgParser:
    def test_flags_exist(self, cli):
        parser = cli.build_arg_parser()
        dests = {action.dest for action in parser._actions}
        assert {"dry_run", "validate_only", "start", "end"} <= dests

    def test_dry_run_and_validate_only_together_is_usage_error(self, cli):
        with pytest.raises(SystemExit) as exc_info:
            cli.main(["--dry-run", "--validate-only"])
        assert exc_info.value.code == 2


class TestMainUsageBoundary:
    def test_bad_start_shape_returns_usage_error(self, cli):
        from src.pipeline.monthly_pipeline import EXIT_USAGE_ERROR

        assert cli.main(["--start", "2025-13"]) == EXIT_USAGE_ERROR

    def test_end_before_start_returns_usage_error(self, cli):
        from src.pipeline.monthly_pipeline import EXIT_USAGE_ERROR

        assert cli.main(["--start", "2025-06", "--end", "2025-01"]) == EXIT_USAGE_ERROR

    def test_valid_args_without_project_is_config_error(self, cli, monkeypatch):
        # Valid shapes -> passes the usage boundary, then fails at config
        # (no GCP_PROJECT_ID), proving the boundary is usage(2) vs config(3).
        from src.pipeline.monthly_pipeline import EXIT_CONFIG_ERROR

        monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
        assert cli.main(["--start", "2025-01", "--end", "2025-03"]) == EXIT_CONFIG_ERROR
