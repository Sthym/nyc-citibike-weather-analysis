"""Pure range parsing and strict whole-range preflight validation for
the Stage 5 multi-month batch pipeline.

No I/O and no BigQuery SDK import -- fully unit-testable with plain
values, same pattern as ``src.pipeline.month_period``. Reuses
``month_period.parse_year_month`` (CLI-shape validation) and
``month_period.parse_month_period`` (live-range validation) rather than
re-implementing either -- this module only adds the batch-specific
concerns: enumerating a start..end range and checking the WHOLE range
up front, before any month is processed.
"""
from __future__ import annotations

from typing import List, Tuple

from src.pipeline.month_period import (
    CliUsageError,
    InvalidMonthPeriodError,
    MonthPeriod,
    parse_month_period,
)


class BatchPreflightError(ValueError):
    """Raised when one or more requested months in the batch do not
    fully fall inside the current live effective shared source range.

    Strict whole-range semantics: ALL requested months are checked (not
    just the first failure), and if ANY month fails, the entire batch is
    rejected before a single month is processed -- no partial batches.
    """


def months_in_range(
    start_year: int, start_month: int, end_year: int, end_month: int
) -> List[Tuple[int, int]]:
    """Enumerate whole (year, month) tuples from start to end, inclusive,
    in chronological order, crossing year boundaries as needed.

    Assumes ``start_year``/``start_month``/``end_year``/``end_month`` are
    already integers with month in 1-12 (the caller's job, via
    ``month_period.parse_year_month`` -- the same division of
    responsibility ``monthly_pipeline.execute`` uses for a single
    year/month). Only the chronological start<=end ordering is checked
    here, raising ``CliUsageError`` (a usage/input-shape problem, exit
    code 2) if violated.
    """
    start_key = (start_year, start_month)
    end_key = (end_year, end_month)
    if end_key < start_key:
        raise CliUsageError(
            f"--end-year/--end-month ({end_year:04d}-{end_month:02d}) must not be "
            f"before --start-year/--start-month ({start_year:04d}-{start_month:02d})"
        )

    months: List[Tuple[int, int]] = []
    year, month = start_year, start_month
    while (year, month) <= end_key:
        months.append((year, month))
        month += 1
        if month == 13:
            month = 1
            year += 1
    return months


def preflight_validate_range(
    months: List[Tuple[int, int]],
    effective_min_date,
    effective_max_date,
) -> List[MonthPeriod]:
    """Validate EVERY requested month against the live effective shared
    source range before any of them is processed.

    Unlike a lazy per-month check (which would let earlier months load
    successfully before discovering a later month is unavailable), this
    collects failures for ALL requested months and raises a single
    ``BatchPreflightError`` listing every one of them if any month is
    invalid -- the batch either runs in full or not at all.

    Returns the ordered list of ``MonthPeriod`` objects (reusing
    ``month_period.parse_month_period``, unchanged) when every month
    passes.
    """
    periods: List[MonthPeriod] = []
    failures: List[str] = []
    for year, month in months:
        try:
            periods.append(parse_month_period(year, month, effective_min_date, effective_max_date))
        except InvalidMonthPeriodError as exc:
            failures.append(str(exc))

    if failures:
        raise BatchPreflightError(
            f"whole-range preflight validation failed for {len(failures)} of "
            f"{len(months)} requested month(s) -- strict mode requires the ENTIRE "
            "range to be covered before any month is processed:\n  "
            + "\n  ".join(failures)
        )

    return periods
