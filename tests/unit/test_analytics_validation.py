"""Unit tests for src/analytics/analytics_validation.py -- pure logic."""
import pytest

from src.analytics.analytics_validation import (
    ObservedAnalyticsData,
    validate_analytics,
)


def make_observed(**overrides):
    base = dict(
        analytics_row_count=3,
        analytics_distinct_dates=3,
        analytics_null_dates=0,
        analytics_sums={
            "num_trips": 100,
            "num_member_trips": 70,
            "num_casual_trips": 30,
            "prcp_inches": 1.5,
            "snow_inches": 0.0,
        },
        analytics_indicator_counts={"count_rainy": 1, "count_snowy": 0, "count_weather_matched": 3},
        source_row_count=3,
        source_distinct_dates=3,
        source_sums={
            "num_trips": 100,
            "num_member_trips": 70,
            "num_casual_trips": 30,
            "prcp_inches": 1.5,
            "snow_inches": 0.0,
        },
        source_indicator_counts={"count_rainy": 1, "count_snowy": 0, "count_weather_matched": 3},
        bad_temperature_band=0,
        bad_rain_category=0,
        bad_snow_category=0,
        temperature_consistency_violations=0,
        rain_consistency_violations=0,
        snow_consistency_violations=0,
    )
    base.update(overrides)
    return ObservedAnalyticsData(**base)


class TestHappyPath:
    def test_passes_when_everything_reconciles(self):
        result = validate_analytics(make_observed())
        assert result.passed is True
        assert result.mismatches == []

    def test_float_within_tolerance_passes(self):
        obs = make_observed(
            source_sums={
                "num_trips": 100,
                "num_member_trips": 70,
                "num_casual_trips": 30,
                "prcp_inches": 1.5 + 1e-9,
                "snow_inches": 0.0,
            }
        )
        assert validate_analytics(obs).passed is True


class TestFailures:
    def test_duplicate_dates_fail(self):
        result = validate_analytics(make_observed(analytics_distinct_dates=2))
        assert result.passed is False
        assert any(m.startswith("A1") for m in result.mismatches)

    def test_null_dates_fail(self):
        result = validate_analytics(make_observed(analytics_null_dates=1))
        assert any(m.startswith("A2") for m in result.mismatches)

    def test_row_count_not_preserved_fails(self):
        result = validate_analytics(make_observed(source_row_count=4))
        assert any(m.startswith("A3") for m in result.mismatches)

    def test_distinct_dates_not_preserved_fails(self):
        # keep A1 satisfied (row_count==distinct), break only A4
        result = validate_analytics(
            make_observed(
                analytics_row_count=4, analytics_distinct_dates=4, source_row_count=4, source_distinct_dates=3
            )
        )
        assert any(m.startswith("A4") for m in result.mismatches)

    def test_member_count_not_preserved_fails(self):
        result = validate_analytics(
            make_observed(
                source_sums={
                    "num_trips": 100,
                    "num_member_trips": 69,
                    "num_casual_trips": 30,
                    "prcp_inches": 1.5,
                    "snow_inches": 0.0,
                }
            )
        )
        assert any(m.startswith("A5") and "num_member_trips" in m for m in result.mismatches)

    def test_weather_measure_not_preserved_fails(self):
        result = validate_analytics(
            make_observed(
                source_sums={
                    "num_trips": 100,
                    "num_member_trips": 70,
                    "num_casual_trips": 30,
                    "prcp_inches": 2.0,
                    "snow_inches": 0.0,
                }
            )
        )
        assert any(m.startswith("A6") and "prcp_inches" in m for m in result.mismatches)

    def test_indicator_not_preserved_fails(self):
        result = validate_analytics(
            make_observed(
                source_indicator_counts={"count_rainy": 2, "count_snowy": 0, "count_weather_matched": 3}
            )
        )
        assert any(m.startswith("A7") and "count_rainy" in m for m in result.mismatches)

    def test_temperature_band_domain_fails(self):
        result = validate_analytics(make_observed(bad_temperature_band=1))
        assert any(m.startswith("A8") for m in result.mismatches)

    def test_rain_category_domain_fails(self):
        result = validate_analytics(make_observed(bad_rain_category=1))
        assert any(m.startswith("A9") for m in result.mismatches)

    def test_snow_category_domain_fails(self):
        result = validate_analytics(make_observed(bad_snow_category=1))
        assert any(m.startswith("A10") for m in result.mismatches)

    def test_consistency_violation_fails(self):
        result = validate_analytics(make_observed(rain_consistency_violations=2))
        assert any(m.startswith("A11") and "rain_category" in m for m in result.mismatches)

    def test_multiple_failures_all_reported(self):
        result = validate_analytics(
            make_observed(analytics_null_dates=1, bad_snow_category=1)
        )
        assert result.passed is False
        assert len(result.mismatches) >= 2
