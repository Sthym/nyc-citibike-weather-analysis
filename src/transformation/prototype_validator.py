"""Pure validation logic for the Stage 3 one-month (January 2025) prototype.

No I/O and no BigQuery SDK imports -- fully unit-testable with plain
dicts/lists, independent of any live connection. Callers (scripts/) are
responsible for running the queries that produce the "observed" data
this module compares.

Rule inventory (V1-V11):
  V1  destination row count == Citi Bike source row count
  V2  no duplicate dates in the destination (row count == distinct dates)
  V3  no null dates in the destination
  V4  destination date range falls within the requested month
  V5  additive Citi Bike columns: SUM(destination) == SUM(source)
  V6  non-additive Citi Bike columns (avg/median/distance): per-date,
      null-safe, tolerance-based comparison
  V7  weather_matched flag is never null, and matched + unmatched ==
      total destination rows
  V8  Citi Bike rider-type reconciliation (member + casual == total) --
      reported as a SOURCE-QUALITY FINDING, not a validation failure.
      Never alters source values.
  V9  Citi Bike geography reconciliation (nyc + jc == total) -- also a
      source-quality finding, not a validation failure.
  V10 non-additive weather columns, compared only for matched dates,
      null-safe and tolerance-based; is_rainy/is_snowy compared against
      CAST(source.is_rainy AS BOOL) / CAST(source.is_snowy AS BOOL)
  V11 domain check: non-null source is_rainy/is_snowy values must be in
      {0, 1} before they are ever cast to BOOL

V8 and V9 are deliberately kept separate from ``mismatches``: they
describe a pre-existing condition in the source data (see DECISIONS.md
D-012), not something introduced by this transformation, so they must
never flip ``passed`` to False on their own.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Sequence, Set

FLOAT_TOLERANCE = 1e-6

# Additive Citi Bike columns -- safe to compare via SUM() (V5).
ADDITIVE_CITIBIKE_COLUMNS = [
    "num_trips",
    "num_member_trips",
    "num_casual_trips",
    "num_member_trips_nyc",
    "num_casual_trips_nyc",
    "num_member_trips_jc",
    "num_casual_trips_jc",
    "num_nyc_trips",
    "num_jc_trips",
    "num_classic_trips",
    "num_electric_trips",
]

# Non-additive Citi Bike columns -- averages/medians/distances must be
# compared per-date, not summed (V6).
NON_ADDITIVE_CITIBIKE_COLUMNS = [
    "avg_trip_duration_minutes",
    "median_trip_duration_minutes",
    "avg_distance_meters",
]

# Non-additive weather columns, split by comparison kind (V10).
NON_ADDITIVE_WEATHER_FLOAT_COLUMNS = [
    "tmin_f",
    "tmax_f",
    "tavg_f",
    "prcp_inches",
    "snow_inches",
]
NON_ADDITIVE_WEATHER_EXACT_COLUMNS = ["is_rainy", "is_snowy", "season"]


@dataclass
class ObservedPrototypeData:
    """Everything ``validate_prototype`` needs, already fetched by the caller."""

    # Structural counts (destination table).
    destination_row_count: int
    distinct_date_count: int
    null_date_count: int
    min_date: date
    max_date: date

    # Weather-match bookkeeping (destination table).
    matched_weather_rows: int
    unmatched_weather_rows: int
    weather_matched_null_count: int

    # Citi Bike source-side counts/sums, scoped to the same month.
    citibike_source_row_count: int
    destination_additive_sums: Dict[str, float]
    source_additive_sums: Dict[str, float]

    # Per-date dicts keyed by date, for row-by-row comparisons.
    destination_rows_by_date: Dict[date, Dict[str, Any]]
    citibike_source_rows_by_date: Dict[date, Dict[str, Any]]
    weather_source_rows_by_date: Dict[date, Dict[str, Any]]

    # Row lists for reconciliation (V8/V9) and domain checks (V11). Each
    # row is a dict that includes at least "date" plus the referenced
    # columns. is_rainy/is_snowy in these rows are the RAW source values
    # (not yet cast to BOOL) so V11 can check their domain.
    citibike_reconciliation_rows: List[Dict[str, Any]] = field(default_factory=list)
    weather_indicator_rows: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class PrototypeValidationResult:
    passed: bool
    mismatches: List[str] = field(default_factory=list)
    source_quality_findings: List[str] = field(default_factory=list)
    matched_weather_rows: Optional[int] = None
    unmatched_weather_rows: Optional[int] = None
    weather_match_rate: Optional[float] = None


def cast_int_indicator_to_bool(value: Optional[int]) -> Optional[bool]:
    """Mirror BigQuery's ``CAST(x AS BOOL)`` semantics for a nullable 0/1
    indicator: NULL stays NULL, 0 -> False, any other non-null value ->
    True (matching BigQuery, which treats any non-zero INT64 as TRUE).
    """
    if value is None:
        return None
    return bool(value)


def _null_safe_float_equal(a: Optional[float], b: Optional[float], tolerance: float = FLOAT_TOLERANCE) -> bool:
    """Null-safe, tolerance-based equality for nullable FLOAT64 values.

    Both null -> equal. Exactly one null -> not equal. Otherwise compare
    within ``tolerance`` rather than exact equality.
    """
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return abs(a - b) < tolerance


def check_row_count(destination_count: int, source_count: int) -> Optional[str]:
    """V1."""
    if destination_count != source_count:
        return (
            f"V1 row_count: destination has {destination_count} rows, "
            f"expected {source_count} (Citi Bike source row count for the month)"
        )
    return None


def check_no_duplicate_dates(destination_count: int, distinct_date_count: int) -> Optional[str]:
    """V2."""
    if destination_count != distinct_date_count:
        return (
            f"V2 duplicate dates: {destination_count} destination rows but only "
            f"{distinct_date_count} distinct dates"
        )
    return None


def check_no_null_dates(null_date_count: int) -> Optional[str]:
    """V3."""
    if null_date_count != 0:
        return f"V3 null_dates: expected 0, got {null_date_count}"
    return None


def check_date_range(min_date: date, max_date: date, expected_start: date, expected_end: date) -> List[str]:
    """V4."""
    issues: List[str] = []
    if min_date < expected_start:
        issues.append(f"V4 min_date {min_date} is before expected start {expected_start}")
    if max_date > expected_end:
        issues.append(f"V4 max_date {max_date} is after expected end {expected_end}")
    return issues


def check_additive_sums(destination_sums: Dict[str, float], source_sums: Dict[str, float]) -> List[str]:
    """V5."""
    mismatches: List[str] = []
    for column in ADDITIVE_CITIBIKE_COLUMNS:
        d = destination_sums.get(column)
        s = source_sums.get(column)
        if d != s:
            mismatches.append(f"V5 {column}: destination SUM={d}, source SUM={s}")
    return mismatches


def check_non_additive_rows(
    destination_rows: Dict[date, Dict[str, Any]],
    source_rows: Dict[date, Dict[str, Any]],
    float_columns: Sequence[str],
    exact_columns: Sequence[str],
    rule_label: str,
    tolerance: float = FLOAT_TOLERANCE,
    only_dates: Optional[Set[date]] = None,
) -> List[str]:
    """Shared row-by-row comparison used by both V6 and V10.

    Float columns use null-safe tolerance comparison; exact columns use
    plain Python equality, which is already null-safe (``None == None``
    is ``True`` in Python, and a null on only one side is correctly
    unequal).
    """
    mismatches: List[str] = []
    dates_to_check = only_dates if only_dates is not None else (set(destination_rows) | set(source_rows))
    for d in sorted(dates_to_check):
        dest = destination_rows.get(d, {})
        src = source_rows.get(d, {})
        for col in float_columns:
            if not _null_safe_float_equal(dest.get(col), src.get(col), tolerance):
                mismatches.append(
                    f"{rule_label} {d}: {col} mismatch (destination={dest.get(col)}, source={src.get(col)})"
                )
        for col in exact_columns:
            if dest.get(col) != src.get(col):
                mismatches.append(
                    f"{rule_label} {d}: {col} mismatch (destination={dest.get(col)}, source={src.get(col)})"
                )
    return mismatches


def check_weather_matched_consistency(
    matched: int, unmatched: int, total: int, null_flag_count: int
) -> List[str]:
    """V7."""
    issues: List[str] = []
    if null_flag_count != 0:
        issues.append(f"V7 weather_matched has {null_flag_count} null value(s), expected none")
    if matched + unmatched != total:
        issues.append(f"V7 matched ({matched}) + unmatched ({unmatched}) != total destination rows ({total})")
    return issues


def check_reconciliation(
    rows: Sequence[Dict[str, Any]],
    component_columns: Sequence[str],
    total_column: str,
    label: str,
) -> List[str]:
    """V8 / V9 -- source-quality findings, NOT validation failures.

    Reports affected dates and the exact difference. Never modifies the
    rows it is given; this is read-only reporting over already-fetched
    source data.
    """
    findings: List[str] = []
    for row in rows:
        total = row[total_column]
        components_sum = sum(row[c] for c in component_columns)
        if components_sum != total:
            diff = total - components_sum
            findings.append(
                f"{label} {row['date']}: {' + '.join(component_columns)} = {components_sum}, "
                f"{total_column} = {total} (difference: {diff})"
            )
    return findings


def check_indicator_domain(rows: Sequence[Dict[str, Any]], column: str, rule_label: str) -> Optional[str]:
    """V11 -- non-null source indicator values must be in {0, 1}."""
    bad_values = sorted(
        {row[column] for row in rows if row.get(column) is not None and row[column] not in (0, 1)}
    )
    if bad_values:
        return f"{rule_label} {column}: found non-null source value(s) outside {{0, 1}}: {bad_values}"
    return None


def validate_prototype(
    observed: ObservedPrototypeData,
    expected_start: date,
    expected_end: date,
) -> PrototypeValidationResult:
    """Run the full V1-V11 rule set and assemble the result.

    V8 and V9 populate ``source_quality_findings`` only -- they never
    affect ``passed``. Every other rule populates ``mismatches`` and can
    fail the overall check.
    """
    mismatches: List[str] = []
    findings: List[str] = []

    m = check_row_count(observed.destination_row_count, observed.citibike_source_row_count)
    if m:
        mismatches.append(m)

    m = check_no_duplicate_dates(observed.destination_row_count, observed.distinct_date_count)
    if m:
        mismatches.append(m)

    m = check_no_null_dates(observed.null_date_count)
    if m:
        mismatches.append(m)

    mismatches.extend(check_date_range(observed.min_date, observed.max_date, expected_start, expected_end))

    mismatches.extend(check_additive_sums(observed.destination_additive_sums, observed.source_additive_sums))

    mismatches.extend(
        check_non_additive_rows(
            observed.destination_rows_by_date,
            observed.citibike_source_rows_by_date,
            float_columns=NON_ADDITIVE_CITIBIKE_COLUMNS,
            exact_columns=[],
            rule_label="V6",
        )
    )

    mismatches.extend(
        check_weather_matched_consistency(
            observed.matched_weather_rows,
            observed.unmatched_weather_rows,
            observed.destination_row_count,
            observed.weather_matched_null_count,
        )
    )

    findings.extend(
        check_reconciliation(
            observed.citibike_reconciliation_rows,
            ["num_member_trips", "num_casual_trips"],
            "num_trips",
            "V8 (rider-type)",
        )
    )
    findings.extend(
        check_reconciliation(
            observed.citibike_reconciliation_rows,
            ["num_nyc_trips", "num_jc_trips"],
            "num_trips",
            "V9 (geography)",
        )
    )

    matched_dates = {
        d for d, row in observed.destination_rows_by_date.items() if row.get("weather_matched")
    }
    mismatches.extend(
        check_non_additive_rows(
            observed.destination_rows_by_date,
            observed.weather_source_rows_by_date,
            float_columns=NON_ADDITIVE_WEATHER_FLOAT_COLUMNS,
            exact_columns=NON_ADDITIVE_WEATHER_EXACT_COLUMNS,
            rule_label="V10",
            only_dates=matched_dates,
        )
    )

    m = check_indicator_domain(observed.weather_indicator_rows, "is_rainy", "V11")
    if m:
        mismatches.append(m)
    m = check_indicator_domain(observed.weather_indicator_rows, "is_snowy", "V11")
    if m:
        mismatches.append(m)

    total = observed.destination_row_count
    match_rate = (observed.matched_weather_rows / total) if total else None

    return PrototypeValidationResult(
        passed=not mismatches,
        mismatches=mismatches,
        source_quality_findings=findings,
        matched_weather_rows=observed.matched_weather_rows,
        unmatched_weather_rows=observed.unmatched_weather_rows,
        weather_match_rate=match_rate,
    )
