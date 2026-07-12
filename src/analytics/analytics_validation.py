"""Pure validation logic for the Stage 6 analytics table.

No I/O and no BigQuery SDK import -- fully unit-testable with plain
dicts, independent of any live connection, mirroring
``src.transformation.prototype_validator``. The caller
(``src.analytics.analytics_pipeline``) runs the aggregate queries that
produce the ``ObservedAnalyticsData`` this module compares: the same set
of aggregates is computed over the loaded analytics table and over the
``UNION ALL`` of the exact monthly source tables it was built from, so
"preserved" means "identical to the rows that went in".

Rule inventory (A1-A11):
  A1  no duplicate dates    (row_count == distinct_dates)
  A2  no null dates         (null_dates == 0)
  A3  row count preserved   (analytics row_count == source row_count)
  A4  distinct dates preserved
  A5  ride counts preserved (num_trips / num_member_trips /
      num_casual_trips SUMs identical, source vs analytics)
  A6  weather measures preserved (prcp_inches / snow_inches SUMs equal
      within float tolerance)
  A7  weather indicators preserved (COUNTIF is_rainy / is_snowy /
      weather_matched identical)
  A8  temperature_band domain (0 rows outside the allowed value set)
  A9  rain_category domain
  A10 snow_category domain
  A11 derived-field <-> input consistency: a category is 'Unknown' if
      and only if its driving input is NULL (0 violations)

Preservation is analytics-vs-source only. It deliberately does NOT
assert num_member_trips + num_casual_trips == num_trips: that rider-type
identity is a known source-data condition reported (never enforced) by
the Stage 3 validator (V8, DECISIONS.md D-012), so Stage 6 must not turn
it into a failure either.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

FLOAT_TOLERANCE = 1e-6

# Ride-count columns compared as exact integer SUMs (A5).
PRESERVED_RIDE_COUNT_COLUMNS = ["num_trips", "num_member_trips", "num_casual_trips"]
# Weather measures compared as float SUMs within tolerance (A6).
PRESERVED_WEATHER_MEASURE_COLUMNS = ["prcp_inches", "snow_inches"]
# Weather indicators compared as exact COUNTIF integers (A7).
PRESERVED_INDICATOR_KEYS = ["count_rainy", "count_snowy", "count_weather_matched"]


@dataclass
class ObservedAnalyticsData:
    """Everything ``validate_analytics`` needs, already fetched by the
    caller. ``*_sums`` dicts are keyed by column name; ``*_indicator_counts``
    by the ``PRESERVED_INDICATOR_KEYS``.
    """

    # Analytics table structural counts.
    analytics_row_count: int
    analytics_distinct_dates: int
    analytics_null_dates: int
    analytics_sums: Dict[str, float]
    analytics_indicator_counts: Dict[str, int]

    # Same aggregates over the UNION ALL of the source monthly tables.
    source_row_count: int
    source_distinct_dates: int
    source_sums: Dict[str, float]
    source_indicator_counts: Dict[str, int]

    # Derived-field domain / consistency violation counts (analytics table).
    bad_temperature_band: int
    bad_rain_category: int
    bad_snow_category: int
    temperature_consistency_violations: int
    rain_consistency_violations: int
    snow_consistency_violations: int


@dataclass
class AnalyticsValidationResult:
    passed: bool
    mismatches: List[str] = field(default_factory=list)


def _null_safe_float_equal(a: Optional[float], b: Optional[float], tolerance: float = FLOAT_TOLERANCE) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return abs(a - b) < tolerance


def check_no_duplicate_dates(row_count: int, distinct_dates: int) -> Optional[str]:
    """A1."""
    if row_count != distinct_dates:
        return f"A1 duplicate dates: {row_count} rows but only {distinct_dates} distinct dates"
    return None


def check_no_null_dates(null_dates: int) -> Optional[str]:
    """A2."""
    if null_dates != 0:
        return f"A2 null_dates: expected 0, got {null_dates}"
    return None


def check_row_count_preserved(analytics_count: int, source_count: int) -> Optional[str]:
    """A3."""
    if analytics_count != source_count:
        return (
            f"A3 row_count: analytics has {analytics_count} rows, "
            f"source union has {source_count}"
        )
    return None


def check_distinct_dates_preserved(analytics_distinct: int, source_distinct: int) -> Optional[str]:
    """A4."""
    if analytics_distinct != source_distinct:
        return (
            f"A4 distinct_dates: analytics has {analytics_distinct}, "
            f"source union has {source_distinct}"
        )
    return None


def check_ride_counts_preserved(analytics_sums: Dict[str, float], source_sums: Dict[str, float]) -> List[str]:
    """A5 -- exact integer SUM comparison."""
    mismatches: List[str] = []
    for column in PRESERVED_RIDE_COUNT_COLUMNS:
        a = analytics_sums.get(column)
        s = source_sums.get(column)
        if a != s:
            mismatches.append(f"A5 {column}: analytics SUM={a}, source SUM={s}")
    return mismatches


def check_weather_measures_preserved(analytics_sums: Dict[str, float], source_sums: Dict[str, float]) -> List[str]:
    """A6 -- float SUM comparison within tolerance."""
    mismatches: List[str] = []
    for column in PRESERVED_WEATHER_MEASURE_COLUMNS:
        a = analytics_sums.get(column)
        s = source_sums.get(column)
        if not _null_safe_float_equal(a, s):
            mismatches.append(f"A6 {column}: analytics SUM={a}, source SUM={s}")
    return mismatches


def check_indicators_preserved(
    analytics_counts: Dict[str, int], source_counts: Dict[str, int]
) -> List[str]:
    """A7 -- exact COUNTIF comparison for the weather indicators."""
    mismatches: List[str] = []
    for key in PRESERVED_INDICATOR_KEYS:
        a = analytics_counts.get(key)
        s = source_counts.get(key)
        if a != s:
            mismatches.append(f"A7 {key}: analytics={a}, source={s}")
    return mismatches


def check_domain(bad_count: int, rule_label: str, column: str) -> Optional[str]:
    """A8/A9/A10 -- a derived column had values outside its allowed set."""
    if bad_count != 0:
        return f"{rule_label} {column}: {bad_count} row(s) with a value outside the allowed set"
    return None


def check_consistency(violation_count: int, rule_label: str, column: str, input_column: str) -> Optional[str]:
    """A11 -- category is 'Unknown' iff its driving input is NULL."""
    if violation_count != 0:
        return (
            f"{rule_label} {column}: {violation_count} row(s) where "
            f"'Unknown' does not match ({input_column} IS NULL)"
        )
    return None


def validate_analytics(observed: ObservedAnalyticsData) -> AnalyticsValidationResult:
    """Run the full A1-A11 rule set and assemble the result. Any populated
    mismatch fails the overall check (``passed`` is False)."""
    mismatches: List[str] = []

    for check in (
        check_no_duplicate_dates(observed.analytics_row_count, observed.analytics_distinct_dates),
        check_no_null_dates(observed.analytics_null_dates),
        check_row_count_preserved(observed.analytics_row_count, observed.source_row_count),
        check_distinct_dates_preserved(observed.analytics_distinct_dates, observed.source_distinct_dates),
    ):
        if check:
            mismatches.append(check)

    mismatches.extend(check_ride_counts_preserved(observed.analytics_sums, observed.source_sums))
    mismatches.extend(check_weather_measures_preserved(observed.analytics_sums, observed.source_sums))
    mismatches.extend(check_indicators_preserved(observed.analytics_indicator_counts, observed.source_indicator_counts))

    for check in (
        check_domain(observed.bad_temperature_band, "A8", "temperature_band"),
        check_domain(observed.bad_rain_category, "A9", "rain_category"),
        check_domain(observed.bad_snow_category, "A10", "snow_category"),
        check_consistency(observed.temperature_consistency_violations, "A11", "temperature_band", "tavg_f"),
        check_consistency(observed.rain_consistency_violations, "A11", "rain_category", "is_rainy"),
        check_consistency(observed.snow_consistency_violations, "A11", "snow_category", "is_snowy"),
    ):
        if check:
            mismatches.append(check)

    return AnalyticsValidationResult(passed=not mismatches, mismatches=mismatches)
