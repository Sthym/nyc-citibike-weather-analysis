from datetime import date

import pytest

from src.pipeline.month_period import (
    CliUsageError,
    InvalidMonthPeriodError,
    compute_effective_range,
    load_destination_config,
    monthly_table_name,
    parse_month_period,
    parse_year_month,
)


class TestMonthlyTableName:
    def test_derives_monthly_prefix_distinct_from_stage3_prototype_prefix(self):
        name = monthly_table_name(2025, 2)
        assert name == "citibike_weather_monthly_2025_02"
        assert "prototype" not in name

    def test_zero_pads_single_digit_month(self):
        assert monthly_table_name(2025, 9) == "citibike_weather_monthly_2025_09"


class TestParseYearMonth:
    def test_valid_integers(self):
        assert parse_year_month(2025, 2) == (2025, 2)

    def test_valid_strings_coerced(self):
        assert parse_year_month("2025", "2") == (2025, 2)

    def test_non_integer_year_raises_usage_error(self):
        with pytest.raises(CliUsageError):
            parse_year_month("not-a-year", 2)

    def test_non_integer_month_raises_usage_error(self):
        with pytest.raises(CliUsageError):
            parse_year_month(2025, "not-a-month")

    def test_month_zero_raises_usage_error(self):
        with pytest.raises(CliUsageError):
            parse_year_month(2025, 0)

    def test_month_thirteen_raises_usage_error(self):
        with pytest.raises(CliUsageError):
            parse_year_month(2025, 13)

    def test_month_boundaries_valid(self):
        assert parse_year_month(2025, 1) == (2025, 1)
        assert parse_year_month(2025, 12) == (2025, 12)


class TestComputeEffectiveRange:
    def test_min_is_the_later_of_the_two_minimums(self):
        effective_min, _ = compute_effective_range(
            date(2013, 6, 1), date(2026, 5, 31), date(1876, 1, 1), date(2026, 5, 29)
        )
        assert effective_min == date(2013, 6, 1)

    def test_max_is_the_earlier_of_the_two_maximums(self):
        _, effective_max = compute_effective_range(
            date(2013, 6, 1), date(2026, 5, 31), date(1876, 1, 1), date(2026, 5, 29)
        )
        assert effective_max == date(2026, 5, 29)


class TestParseMonthPeriod:
    EFFECTIVE_MIN = date(2013, 6, 1)
    EFFECTIVE_MAX = date(2026, 5, 29)

    def test_fully_contained_month_is_valid(self):
        period = parse_month_period(2025, 2, self.EFFECTIVE_MIN, self.EFFECTIVE_MAX)
        assert period.start_date == date(2025, 2, 1)
        assert period.end_date == date(2025, 2, 28)

    def test_month_before_effective_min_rejected(self):
        with pytest.raises(InvalidMonthPeriodError):
            parse_month_period(2010, 1, self.EFFECTIVE_MIN, self.EFFECTIVE_MAX)

    def test_month_entirely_after_effective_max_rejected(self):
        with pytest.raises(InvalidMonthPeriodError):
            parse_month_period(2027, 1, self.EFFECTIVE_MIN, self.EFFECTIVE_MAX)

    def test_partial_month_straddling_effective_max_is_rejected_not_truncated(self):
        # effective_max is 2026-05-29; May 2026 spans 05-01..05-31, so
        # it partially overlaps but is NOT fully contained -- must reject.
        with pytest.raises(InvalidMonthPeriodError):
            parse_month_period(2026, 5, self.EFFECTIVE_MIN, self.EFFECTIVE_MAX)

    def test_first_available_month_boundary_is_valid(self):
        # effective_min is 2013-06-01, exactly the first day of June 2013.
        period = parse_month_period(2013, 6, self.EFFECTIVE_MIN, self.EFFECTIVE_MAX)
        assert period.start_date == self.EFFECTIVE_MIN

    def test_month_entirely_before_min_but_same_year_rejected(self):
        with pytest.raises(InvalidMonthPeriodError):
            parse_month_period(2013, 5, self.EFFECTIVE_MIN, self.EFFECTIVE_MAX)


class TestLoadDestinationConfig:
    def test_requires_destination_dataset(self):
        with pytest.raises(ValueError):
            load_destination_config(env={}, default_project="proj")

    def test_destination_project_falls_back_to_default(self):
        project, dataset = load_destination_config(
            env={"BQ_DESTINATION_DATASET": "ds"}, default_project="fallback-proj"
        )
        assert project == "fallback-proj"
        assert dataset == "ds"

    def test_explicit_destination_project_overrides_default(self):
        project, dataset = load_destination_config(
            env={"BQ_DESTINATION_DATASET": "ds", "BQ_DESTINATION_PROJECT_ID": "explicit-proj"},
            default_project="fallback-proj",
        )
        assert project == "explicit-proj"

    def test_requires_some_project_when_no_default_given(self):
        with pytest.raises(ValueError):
            load_destination_config(env={"BQ_DESTINATION_DATASET": "ds"}, default_project=None)
