"""CLI-layer tests for scripts/run_monthly_pipeline.py and
scripts/run_prototype_january_2025.py.

Only exercises argparse-level behavior (usage errors, mutual exclusion)
-- these are intercepted by argparse itself, before any config loading
or BigQuery call, so these tests need no network access and no
environment variables. Business logic (exit codes 3-7) is covered
separately in test_monthly_pipeline.py against src.pipeline.monthly_pipeline.execute.
"""
import importlib.util
import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load_script(name: str, filename: str):
    path = os.path.join(REPO_ROOT, "scripts", filename)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def monthly_script():
    return _load_script("run_monthly_pipeline_under_test", "run_monthly_pipeline.py")


@pytest.fixture(scope="module")
def january_script():
    return _load_script("run_prototype_january_2025_under_test", "run_prototype_january_2025.py")


class TestRunMonthlyPipelineCli:
    def test_missing_year_and_month_is_usage_error(self, monthly_script):
        with pytest.raises(SystemExit) as exc_info:
            monthly_script.main([])
        assert exc_info.value.code == 2

    def test_non_integer_year_is_usage_error(self, monthly_script):
        with pytest.raises(SystemExit) as exc_info:
            monthly_script.main(["--year", "not-a-year", "--month", "2"])
        assert exc_info.value.code == 2

    def test_dry_run_and_validate_only_together_is_usage_error(self, monthly_script):
        with pytest.raises(SystemExit) as exc_info:
            monthly_script.main(["--year", "2025", "--month", "2", "--dry-run", "--validate-only"])
        assert exc_info.value.code == 2

    def test_month_out_of_range_returns_usage_error_without_raising(self, monthly_script):
        # Month range (1-12) is checked by parse_year_month AFTER
        # argparse, so this returns EXIT_USAGE_ERROR rather than raising
        # SystemExit directly.
        from src.pipeline.monthly_pipeline import EXIT_USAGE_ERROR

        result = monthly_script.main(["--year", "2025", "--month", "13"])
        assert result == EXIT_USAGE_ERROR

    def test_valid_month_boundary_does_not_trigger_usage_error(self, monthly_script, monkeypatch):
        # No GCP_PROJECT_ID set -- should fail at the config stage (3),
        # NOT at the usage stage (2), proving month=12 itself is accepted.
        from src.pipeline.monthly_pipeline import EXIT_CONFIG_ERROR

        monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
        result = monthly_script.main(["--year", "2025", "--month", "12"])
        assert result == EXIT_CONFIG_ERROR


class TestRunPrototypeJanuary2025Cli:
    def test_dry_run_and_validate_only_together_is_usage_error(self, january_script):
        with pytest.raises(SystemExit) as exc_info:
            january_script.main(["--dry-run", "--validate-only"])
        assert exc_info.value.code == 2

    def test_no_year_month_flags_exist(self, january_script):
        # The compatibility wrapper takes no --year/--month -- confirms
        # year/month are fixed, not user-overridable.
        parser = january_script.build_arg_parser()
        flag_strings = {action.option_strings[0] for action in parser._actions if action.option_strings}
        assert "--year" not in flag_strings
        assert "--month" not in flag_strings

    def test_missing_config_returns_config_error_not_usage_error(self, january_script, monkeypatch):
        from src.pipeline.monthly_pipeline import EXIT_CONFIG_ERROR

        monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
        result = january_script.main([])
        assert result == EXIT_CONFIG_ERROR
