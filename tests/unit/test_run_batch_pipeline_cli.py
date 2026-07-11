"""CLI-layer tests for scripts/run_batch_pipeline.py.

Only exercises argparse-level and range-order-level behavior (usage
errors, mutual exclusion, chronological ordering) -- these are all
intercepted before any config loading or BigQuery call, so these tests
need no network access and no environment variables (except explicitly
unsetting GCP_PROJECT_ID to prove the boundary between usage errors and
config errors). Batch control-flow logic (exit codes 0/5/6/7/8) is
covered separately in test_batch_pipeline.py against
src.pipeline.batch_pipeline.execute_batch.
"""
import importlib.util
import os

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load_script(name: str, filename: str):
    path = os.path.join(REPO_ROOT, "scripts", filename)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def batch_script():
    return _load_script("run_batch_pipeline_under_test", "run_batch_pipeline.py")


class TestRunBatchPipelineCli:
    def test_missing_required_args_is_usage_error(self, batch_script):
        with pytest.raises(SystemExit) as exc_info:
            batch_script.main([])
        assert exc_info.value.code == 2

    def test_non_integer_year_is_usage_error(self, batch_script):
        with pytest.raises(SystemExit) as exc_info:
            batch_script.main(
                ["--start-year", "nope", "--start-month", "1", "--end-year", "2025", "--end-month", "2"]
            )
        assert exc_info.value.code == 2

    def test_dry_run_and_validate_only_together_is_usage_error(self, batch_script):
        with pytest.raises(SystemExit) as exc_info:
            batch_script.main(
                [
                    "--start-year", "2025", "--start-month", "1",
                    "--end-year", "2025", "--end-month", "2",
                    "--dry-run", "--validate-only",
                ]
            )
        assert exc_info.value.code == 2

    def test_month_out_of_range_returns_usage_error_without_raising(self, batch_script):
        # Month range (1-12) is checked by parse_year_month AFTER
        # argparse, so this returns EXIT_USAGE_ERROR rather than raising
        # SystemExit directly -- same pattern as run_monthly_pipeline.py.
        from src.pipeline.monthly_pipeline import EXIT_USAGE_ERROR

        result = batch_script.main(
            ["--start-year", "2025", "--start-month", "13", "--end-year", "2025", "--end-month", "2"]
        )
        assert result == EXIT_USAGE_ERROR

    def test_end_before_start_returns_usage_error_without_raising(self, batch_script):
        from src.pipeline.monthly_pipeline import EXIT_USAGE_ERROR

        result = batch_script.main(
            ["--start-year", "2025", "--start-month", "6", "--end-year", "2025", "--end-month", "1"]
        )
        assert result == EXIT_USAGE_ERROR

    def test_end_before_start_across_years_returns_usage_error(self, batch_script):
        from src.pipeline.monthly_pipeline import EXIT_USAGE_ERROR

        result = batch_script.main(
            ["--start-year", "2025", "--start-month", "1", "--end-year", "2024", "--end-month", "12"]
        )
        assert result == EXIT_USAGE_ERROR

    def test_continue_on_error_flag_exists(self, batch_script):
        parser = batch_script.build_arg_parser()
        flag_strings = {action.option_strings[0] for action in parser._actions if action.option_strings}
        assert "--continue-on-error" in flag_strings

    def test_log_dir_flag_exists_with_default(self, batch_script):
        parser = batch_script.build_arg_parser()
        actions = {action.dest: action for action in parser._actions}
        assert "log_dir" in actions
        assert actions["log_dir"].default == batch_script.DEFAULT_LOG_DIR

    def test_valid_range_does_not_trigger_usage_error(self, batch_script, monkeypatch):
        # No GCP_PROJECT_ID set -- should fail at the config stage (3),
        # NOT at the usage stage (2), proving a valid chronological
        # range and valid month shapes are accepted.
        from src.pipeline.monthly_pipeline import EXIT_CONFIG_ERROR

        monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
        result = batch_script.main(
            ["--start-year", "2025", "--start-month", "1", "--end-year", "2025", "--end-month", "3"]
        )
        assert result == EXIT_CONFIG_ERROR

    def test_same_start_and_end_month_is_valid_shape(self, batch_script, monkeypatch):
        from src.pipeline.monthly_pipeline import EXIT_CONFIG_ERROR

        monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
        result = batch_script.main(
            ["--start-year", "2025", "--start-month", "6", "--end-year", "2025", "--end-month", "6"]
        )
        assert result == EXIT_CONFIG_ERROR
