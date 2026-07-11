from datetime import date

import pytest

from src.pipeline.batch_period import (
    BatchPreflightError,
    months_in_range,
    preflight_validate_range,
)
from src.pipeline.month_period import CliUsageError


class TestMonthsInRange:
    def test_single_month(self):
        assert months_in_range(2025, 6, 2025, 6) == [(2025, 6)]

    def test_multi_month_same_year(self):
        assert months_in_range(2025, 1, 2025, 3) == [(2025, 1), (2025, 2), (2025, 3)]

    def test_spans_year_boundary(self):
        assert months_in_range(2024, 11, 2025, 2) == [
            (2024, 11),
            (2024, 12),
            (2025, 1),
            (2025, 2),
        ]

    def test_spans_multiple_year_boundaries(self):
        result = months_in_range(2023, 12, 2025, 1)
        assert result[0] == (2023, 12)
        assert result[-1] == (2025, 1)
        assert len(result) == 14

    def test_end_before_start_same_year_raises_usage_error(self):
        with pytest.raises(CliUsageError):
            months_in_range(2025, 6, 2025, 1)

    def test_end_before_start_across_years_raises_usage_error(self):
        with pytest.raises(CliUsageError):
            months_in_range(2025, 1, 2024, 12)


class TestPreflightValidateRange:
    EFFECTIVE_MIN = date(2013, 6, 1)
    EFFECTIVE_MAX = date(2025, 5, 31)

    def test_all_valid_returns_month_periods_in_order(self):
        months = [(2025, 1), (2025, 2), (2025, 3)]
        periods = preflight_validate_range(months, self.EFFECTIVE_MIN, self.EFFECTIVE_MAX)
        assert [(p.year, p.month) for p in periods] == months

    def test_one_invalid_month_fails_whole_range(self):
        months = [(2025, 1), (2025, 6)]  # 2025-06 is beyond effective max (2025-05-31)
        with pytest.raises(BatchPreflightError):
            preflight_validate_range(months, self.EFFECTIVE_MIN, self.EFFECTIVE_MAX)

    def test_no_months_processed_before_raising(self):
        # preflight_validate_range is pure -- it never calls anything
        # that would "process" a month; this just documents that a
        # failure raises before returning any periods at all.
        months = [(2025, 1), (2025, 6)]
        with pytest.raises(BatchPreflightError):
            preflight_validate_range(months, self.EFFECTIVE_MIN, self.EFFECTIVE_MAX)

    def test_error_message_lists_every_invalid_month_not_just_first(self):
        months = [(2025, 6), (2025, 7), (2025, 2)]
        with pytest.raises(BatchPreflightError) as exc_info:
            preflight_validate_range(months, self.EFFECTIVE_MIN, self.EFFECTIVE_MAX)
        message = str(exc_info.value)
        assert "2025-06" in message
        assert "2025-07" in message

    def test_partial_month_at_effective_boundary_rejected(self):
        months = [(2025, 5)]
        with pytest.raises(BatchPreflightError):
            preflight_validate_range(months, self.EFFECTIVE_MIN, date(2025, 5, 15))
