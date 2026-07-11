from datetime import date

import pytest

from src.transformation.prototype_validator import (
    ADDITIVE_CITIBIKE_COLUMNS,
    ObservedPrototypeData,
    cast_int_indicator_to_bool,
    check_indicator_domain,
    check_reconciliation,
    validate_prototype,
)

D1 = date(2025, 1, 1)  # weather-matched date
D2 = date(2025, 1, 2)  # weather-unmatched date
EXPECTED_START = date(2025, 1, 1)
EXPECTED_END = date(2025, 1, 31)


def make_base_observed() -> ObservedPrototypeData:
    """A fully-consistent, passing fixture: 2 destination rows, one with
    a weather match (D1) and one without (D2, mirroring how an
    unmatched date has no weather source row at all).
    """
    destination_rows_by_date = {
        D1: {
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
        },
        D2: {
            "date": D2,
            "avg_trip_duration_minutes": 16.0,
            "median_trip_duration_minutes": 13.0,
            "avg_distance_meters": 2100.0,
            "weather_matched": False,
            "tmin_f": None,
            "tmax_f": None,
            "tavg_f": None,
            "prcp_inches": None,
            "is_rainy": None,
            "snow_inches": None,
            "is_snowy": None,
            "season": None,
        },
    }

    citibike_source_rows_by_date = {
        D1: {
            "date": D1,
            "avg_trip_duration_minutes": 15.0,
            "median_trip_duration_minutes": 12.0,
            "avg_distance_meters": 2000.0,
        },
        D2: {
            "date": D2,
            "avg_trip_duration_minutes": 16.0,
            "median_trip_duration_minutes": 13.0,
            "avg_distance_meters": 2100.0,
        },
    }

    # D2 has no weather source row -- it's genuinely unmatched.
    weather_source_rows_by_date = {
        D1: {
            "date": D1,
            "tmin_f": 30.0,
            "tmax_f": 40.0,
            "tavg_f": 35.0,
            "prcp_inches": 0.1,
            "snow_inches": 0.0,
            "is_rainy": True,   # already cast, as the script does before calling validate_prototype
            "is_snowy": False,
            "season": "Winter",
        },
    }

    citibike_reconciliation_rows = [
        {
            "date": D1,
            "num_member_trips": 80,
            "num_casual_trips": 20,
            "num_nyc_trips": 90,
            "num_jc_trips": 10,
            "num_trips": 100,
        },
        {
            "date": D2,
            "num_member_trips": 50,
            "num_casual_trips": 50,
            "num_nyc_trips": 70,
            "num_jc_trips": 30,
            "num_trips": 100,
        },
    ]

    # RAW (un-cast) source indicator values, as fetched from BigQuery.
    weather_indicator_rows = [
        {"date": D1, "is_rainy": 1, "is_snowy": 0},
    ]

    additive_sums = {col: 10 for col in ADDITIVE_CITIBIKE_COLUMNS}

    return ObservedPrototypeData(
        destination_row_count=2,
        distinct_date_count=2,
        null_date_count=0,
        min_date=D1,
        max_date=D2,
        matched_weather_rows=1,
        unmatched_weather_rows=1,
        weather_matched_null_count=0,
        citibike_source_row_count=2,
        destination_additive_sums=dict(additive_sums),
        source_additive_sums=dict(additive_sums),
        destination_rows_by_date=destination_rows_by_date,
        citibike_source_rows_by_date=citibike_source_rows_by_date,
        weather_source_rows_by_date=weather_source_rows_by_date,
        citibike_reconciliation_rows=citibike_reconciliation_rows,
        weather_indicator_rows=weather_indicator_rows,
    )


class TestBaseCase:
    def test_fully_consistent_fixture_passes(self):
        result = validate_prototype(make_base_observed(), EXPECTED_START, EXPECTED_END)
        assert result.passed is True
        assert result.mismatches == []
        assert result.source_quality_findings == []

    def test_match_rate_computed(self):
        result = validate_prototype(make_base_observed(), EXPECTED_START, EXPECTED_END)
        assert result.matched_weather_rows == 1
        assert result.unmatched_weather_rows == 1
        assert result.weather_match_rate == pytest.approx(0.5)

    def test_match_rate_none_when_no_rows(self):
        observed = make_base_observed()
        observed.destination_row_count = 0
        observed.matched_weather_rows = 0
        observed.unmatched_weather_rows = 0
        result = validate_prototype(observed, EXPECTED_START, EXPECTED_END)
        assert result.weather_match_rate is None


class TestV1RowCount:
    def test_mismatch_fails(self):
        observed = make_base_observed()
        observed.citibike_source_row_count = 3
        result = validate_prototype(observed, EXPECTED_START, EXPECTED_END)
        assert result.passed is False
        assert any("V1 row_count" in m for m in result.mismatches)


class TestV2DuplicateDates:
    def test_mismatch_fails(self):
        observed = make_base_observed()
        observed.distinct_date_count = 1
        result = validate_prototype(observed, EXPECTED_START, EXPECTED_END)
        assert result.passed is False
        assert any("V2 duplicate dates" in m for m in result.mismatches)


class TestV3NullDates:
    def test_mismatch_fails(self):
        observed = make_base_observed()
        observed.null_date_count = 1
        result = validate_prototype(observed, EXPECTED_START, EXPECTED_END)
        assert result.passed is False
        assert any("V3 null_dates" in m for m in result.mismatches)


class TestV4DateRange:
    def test_min_date_before_expected_start_fails(self):
        observed = make_base_observed()
        observed.min_date = date(2024, 12, 31)
        result = validate_prototype(observed, EXPECTED_START, EXPECTED_END)
        assert result.passed is False
        assert any("V4 min_date" in m for m in result.mismatches)

    def test_max_date_after_expected_end_fails(self):
        observed = make_base_observed()
        observed.max_date = date(2025, 2, 1)
        result = validate_prototype(observed, EXPECTED_START, EXPECTED_END)
        assert result.passed is False
        assert any("V4 max_date" in m for m in result.mismatches)


class TestV5AdditiveSums:
    def test_sum_mismatch_reports_only_affected_column(self):
        observed = make_base_observed()
        observed.destination_additive_sums["num_trips"] = 999
        result = validate_prototype(observed, EXPECTED_START, EXPECTED_END)
        assert result.passed is False
        mismatches = [m for m in result.mismatches if m.startswith("V5")]
        assert len(mismatches) == 1
        assert "num_trips" in mismatches[0]


class TestV6NonAdditiveCitibike:
    def test_value_mismatch_reports_date_and_column(self):
        observed = make_base_observed()
        observed.destination_rows_by_date[D1]["avg_trip_duration_minutes"] = 99.0
        result = validate_prototype(observed, EXPECTED_START, EXPECTED_END)
        assert result.passed is False
        assert any(
            "V6" in m and str(D1) in m and "avg_trip_duration_minutes" in m
            for m in result.mismatches
        )

    def test_both_null_is_null_safe_and_passes(self):
        observed = make_base_observed()
        observed.destination_rows_by_date[D1]["avg_trip_duration_minutes"] = None
        observed.citibike_source_rows_by_date[D1]["avg_trip_duration_minutes"] = None
        result = validate_prototype(observed, EXPECTED_START, EXPECTED_END)
        assert result.passed is True

    def test_one_sided_null_fails(self):
        observed = make_base_observed()
        observed.destination_rows_by_date[D1]["avg_trip_duration_minutes"] = None
        result = validate_prototype(observed, EXPECTED_START, EXPECTED_END)
        assert result.passed is False

    def test_within_tolerance_passes(self):
        observed = make_base_observed()
        observed.destination_rows_by_date[D1]["avg_trip_duration_minutes"] = 15.0000001
        result = validate_prototype(observed, EXPECTED_START, EXPECTED_END)
        assert result.passed is True

    def test_beyond_tolerance_fails(self):
        observed = make_base_observed()
        observed.destination_rows_by_date[D1]["avg_trip_duration_minutes"] = 15.01
        result = validate_prototype(observed, EXPECTED_START, EXPECTED_END)
        assert result.passed is False


class TestV7WeatherMatchedConsistency:
    def test_null_flag_count_fails(self):
        observed = make_base_observed()
        observed.weather_matched_null_count = 1
        result = validate_prototype(observed, EXPECTED_START, EXPECTED_END)
        assert result.passed is False
        assert any("V7" in m and "null value" in m for m in result.mismatches)

    def test_matched_plus_unmatched_not_equal_total_fails(self):
        observed = make_base_observed()
        observed.unmatched_weather_rows = 5
        result = validate_prototype(observed, EXPECTED_START, EXPECTED_END)
        assert result.passed is False
        assert any("V7" in m and "!=" in m for m in result.mismatches)


class TestV8V9ReconciliationFindingsNotFailures:
    def test_rider_type_mismatch_is_a_finding_not_a_failure(self):
        observed = make_base_observed()
        observed.citibike_reconciliation_rows[0]["num_member_trips"] = 999
        result = validate_prototype(observed, EXPECTED_START, EXPECTED_END)
        # Must be reported as a source-quality finding...
        assert any("V8" in f and str(D1) in f for f in result.source_quality_findings)
        # ...and must NOT appear in mismatches or flip passed to False.
        assert not any("V8" in m for m in result.mismatches)
        assert result.passed is True

    def test_geography_mismatch_is_a_finding_not_a_failure(self):
        observed = make_base_observed()
        observed.citibike_reconciliation_rows[0]["num_nyc_trips"] = 999
        result = validate_prototype(observed, EXPECTED_START, EXPECTED_END)
        assert any("V9" in f and str(D1) in f for f in result.source_quality_findings)
        assert not any("V9" in m for m in result.mismatches)
        assert result.passed is True

    def test_finding_reports_exact_difference(self):
        rows = [
            {
                "date": D1,
                "num_member_trips": 80,
                "num_casual_trips": 15,  # 80 + 15 = 95; total says 100 -> diff = 100 - 95 = 5
                "num_nyc_trips": 90,
                "num_jc_trips": 10,
                "num_trips": 100,
            }
        ]
        findings = check_reconciliation(rows, ["num_member_trips", "num_casual_trips"], "num_trips", "V8")
        assert len(findings) == 1
        assert "difference: 5" in findings[0]

    def test_source_values_are_never_mutated(self):
        rows = [
            {
                "date": D1,
                "num_member_trips": 80,
                "num_casual_trips": 15,
                "num_nyc_trips": 90,
                "num_jc_trips": 10,
                "num_trips": 100,
            }
        ]
        before = dict(rows[0])
        check_reconciliation(rows, ["num_member_trips", "num_casual_trips"], "num_trips", "V8")
        assert rows[0] == before


class TestV10WeatherRowComparison:
    def test_float_mismatch_on_matched_date_fails(self):
        observed = make_base_observed()
        observed.weather_source_rows_by_date[D1]["tmax_f"] = 999.0
        result = validate_prototype(observed, EXPECTED_START, EXPECTED_END)
        assert result.passed is False
        assert any("V10" in m and str(D1) in m and "tmax_f" in m for m in result.mismatches)

    def test_unmatched_date_absence_is_not_flagged(self):
        # D2 is unmatched and has no weather_source_rows_by_date entry at
        # all -- V10 must only check matched dates, so this must pass.
        result = validate_prototype(make_base_observed(), EXPECTED_START, EXPECTED_END)
        assert not any("V10" in m and str(D2) in m for m in result.mismatches)

    def test_boolean_indicator_mismatch_fails(self):
        observed = make_base_observed()
        observed.weather_source_rows_by_date[D1]["is_rainy"] = False  # destination has True
        result = validate_prototype(observed, EXPECTED_START, EXPECTED_END)
        assert result.passed is False
        assert any("V10" in m and "is_rainy" in m for m in result.mismatches)

    def test_boolean_indicator_match_passes(self):
        # Base fixture already has destination.is_rainy == True and
        # weather_source (cast) is_rainy == True -- confirms the CAST(...
        # AS BOOL) comparison basis works when both sides agree.
        result = validate_prototype(make_base_observed(), EXPECTED_START, EXPECTED_END)
        assert result.passed is True

    def test_season_exact_mismatch_fails(self):
        observed = make_base_observed()
        observed.weather_source_rows_by_date[D1]["season"] = "Summer"
        result = validate_prototype(observed, EXPECTED_START, EXPECTED_END)
        assert result.passed is False
        assert any("V10" in m and "season" in m for m in result.mismatches)


class TestV11IndicatorDomain:
    def test_out_of_domain_value_fails(self):
        observed = make_base_observed()
        observed.weather_indicator_rows = [{"date": D1, "is_rainy": 2, "is_snowy": 0}]
        result = validate_prototype(observed, EXPECTED_START, EXPECTED_END)
        assert result.passed is False
        assert any("V11" in m and "is_rainy" in m and "2" in m for m in result.mismatches)

    def test_null_values_are_ignored(self):
        observed = make_base_observed()
        observed.weather_indicator_rows = [{"date": D1, "is_rainy": None, "is_snowy": None}]
        result = validate_prototype(observed, EXPECTED_START, EXPECTED_END)
        assert result.passed is True

    def test_zero_and_one_are_valid(self):
        result = check_indicator_domain(
            [{"is_rainy": 0}, {"is_rainy": 1}, {"is_rainy": None}], "is_rainy", "V11"
        )
        assert result is None

    def test_direct_helper_reports_bad_values(self):
        result = check_indicator_domain(
            [{"is_snowy": 0}, {"is_snowy": 5}, {"is_snowy": -1}], "is_snowy", "V11"
        )
        assert result is not None
        assert "-1" in result and "5" in result


class TestCastIntIndicatorToBool:
    def test_none_stays_none(self):
        assert cast_int_indicator_to_bool(None) is None

    def test_zero_is_false(self):
        assert cast_int_indicator_to_bool(0) is False

    def test_one_is_true(self):
        assert cast_int_indicator_to_bool(1) is True
