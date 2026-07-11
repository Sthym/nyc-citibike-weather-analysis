from datetime import date

from src.extraction.metadata_validator import (
    CITIBIKE_EXPECTED,
    WEATHER_EXPECTED,
    validate_table_metadata,
)


def _matching_observed(expected):
    return {
        "row_count": expected.row_count,
        "distinct_dates": expected.distinct_dates,
        "null_dates": 0,
        "min_date": expected.min_date,
        "max_date": expected.max_date,
    }


def test_citibike_matches_expected():
    observed = _matching_observed(CITIBIKE_EXPECTED)
    result = validate_table_metadata("citibike", observed, CITIBIKE_EXPECTED)
    assert result.passed is True
    assert result.mismatches == []


def test_weather_matches_expected():
    observed = _matching_observed(WEATHER_EXPECTED)
    result = validate_table_metadata("weather", observed, WEATHER_EXPECTED)
    assert result.passed is True
    assert result.mismatches == []


def test_row_count_mismatch_reported():
    observed = _matching_observed(CITIBIKE_EXPECTED)
    observed["row_count"] = CITIBIKE_EXPECTED.row_count + 1
    # Keep distinct_dates equal to the (wrong) row_count so this test
    # isolates the "drifted from Stage 1 expectation" case from the
    # internal-consistency case, which has its own dedicated test below.
    observed["distinct_dates"] = observed["row_count"]

    result = validate_table_metadata("citibike", observed, CITIBIKE_EXPECTED)

    assert result.passed is False
    assert any(m.startswith("row_count:") for m in result.mismatches)


def test_date_range_mismatch_reported():
    observed = _matching_observed(CITIBIKE_EXPECTED)
    observed["min_date"] = date(2013, 1, 1)

    result = validate_table_metadata("citibike", observed, CITIBIKE_EXPECTED)

    assert result.passed is False
    assert any(m.startswith("min_date:") for m in result.mismatches)


def test_null_dates_nonzero_fails_validation():
    observed = _matching_observed(CITIBIKE_EXPECTED)
    observed["null_dates"] = 3

    result = validate_table_metadata("citibike", observed, CITIBIKE_EXPECTED)

    assert result.passed is False
    assert any("null_dates" in m for m in result.mismatches)


def test_row_count_distinct_dates_internal_mismatch():
    observed = _matching_observed(CITIBIKE_EXPECTED)
    observed["distinct_dates"] = CITIBIKE_EXPECTED.distinct_dates - 1
    # row_count is left unchanged -> now row_count != distinct_dates

    result = validate_table_metadata("citibike", observed, CITIBIKE_EXPECTED)

    assert result.passed is False
    assert any("internal inconsistency" in m for m in result.mismatches)
    # the plain distinct_dates-vs-expected mismatch should also appear
    assert any(m.startswith("distinct_dates:") for m in result.mismatches)


def test_multiple_mismatches_all_reported():
    observed = _matching_observed(CITIBIKE_EXPECTED)
    observed["row_count"] = CITIBIKE_EXPECTED.row_count + 5
    observed["distinct_dates"] = CITIBIKE_EXPECTED.distinct_dates + 5
    observed["null_dates"] = 2
    observed["max_date"] = date(2026, 6, 1)

    result = validate_table_metadata("citibike", observed, CITIBIKE_EXPECTED)

    assert result.passed is False
    assert len(result.mismatches) >= 3
