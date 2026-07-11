"""Pure comparison logic: observed BigQuery metadata vs. Stage 1 findings.

No I/O and no BigQuery SDK imports here -- fully unit-testable with
plain dicts, independent of any live connection.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List


@dataclass(frozen=True)
class TableExpectation:
    row_count: int
    distinct_dates: int
    min_date: date
    max_date: date


@dataclass
class ValidationResult:
    table: str
    passed: bool
    mismatches: List[str]
    observed: Dict[str, Any]
    expected: Dict[str, Any]


# Verified Stage 1 findings -- see DATA_DICTIONARY.md Sections 1a/4 and
# DECISIONS.md D-005, D-010.
CITIBIKE_EXPECTED = TableExpectation(
    row_count=4738,
    distinct_dates=4738,
    min_date=date(2013, 6, 1),
    max_date=date(2026, 5, 31),
)

WEATHER_EXPECTED = TableExpectation(
    row_count=54912,
    distinct_dates=54912,
    min_date=date(1876, 1, 1),
    max_date=date(2026, 5, 29),
)


def validate_table_metadata(
    table: str, observed: Dict[str, Any], expected: TableExpectation
) -> ValidationResult:
    """Compare observed table metadata against verified Stage 1 expectations.

    Runs two kinds of checks:
      1. Internal consistency of the observed data itself (independent
         of what Stage 1 expected).
      2. Drift of the observed data from the Stage 1 expected constants.
    Every failing check is reported -- not just the first.
    """
    mismatches: List[str] = []

    # --- Internal consistency checks ---
    if observed.get("null_dates", 0) != 0:
        mismatches.append(
            f"null_dates: expected 0, got {observed['null_dates']} -- "
            f"NULL values found in the date column"
        )

    if observed["row_count"] != observed["distinct_dates"]:
        mismatches.append(
            f"internal inconsistency: row_count ({observed['row_count']}) != "
            f"distinct_dates ({observed['distinct_dates']}); a daily-grain "
            f"table must have exactly one row per date"
        )

    # --- Comparison against verified Stage 1 expectations ---
    if observed["row_count"] != expected.row_count:
        mismatches.append(
            f"row_count: expected {expected.row_count}, got {observed['row_count']}"
        )
    if observed["distinct_dates"] != expected.distinct_dates:
        mismatches.append(
            f"distinct_dates: expected {expected.distinct_dates}, "
            f"got {observed['distinct_dates']}"
        )
    if observed["min_date"] != expected.min_date:
        mismatches.append(
            f"min_date: expected {expected.min_date}, got {observed['min_date']}"
        )
    if observed["max_date"] != expected.max_date:
        mismatches.append(
            f"max_date: expected {expected.max_date}, got {observed['max_date']}"
        )

    return ValidationResult(
        table=table,
        passed=not mismatches,
        mismatches=mismatches,
        observed=dict(observed),
        expected=vars(expected),
    )
