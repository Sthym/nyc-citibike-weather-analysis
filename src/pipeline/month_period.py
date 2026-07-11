"""Pure CLI-input and month/date validation for the Stage 4 monthly pipeline.

No I/O and no BigQuery SDK import -- fully unit-testable with plain
values. Callers (scripts/, monthly_pipeline.py) are responsible for
fetching the LIVE source date ranges (via the unchanged Stage 2
``BigQueryReadOnlyClient.get_date_range_stats``) and passing them in;
this module never assumes a hardcoded or wall-clock-derived boundary.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from typing import Mapping, Optional, Tuple

from src.transformation.prototype_query import month_range


class CliUsageError(ValueError):
    """Raised for malformed --year/--month input (not integers, month
    outside 1-12). This is a pure input-shape problem, distinct from
    ``InvalidMonthPeriodError`` (a well-formed month that the live
    source range doesn't cover).
    """


class InvalidMonthPeriodError(ValueError):
    """Raised when a well-formed year/month does not fully fall inside
    the current live effective shared source range (see
    ``compute_effective_range``). Partial-month overlap is rejected --
    the ENTIRE month must lie inside the shared range.
    """


@dataclass(frozen=True)
class MonthPeriod:
    year: int
    month: int
    start_date: date
    end_date: date


def monthly_table_name(year: int, month: int) -> str:
    """Stage 4's destination naming convention -- distinct from Stage
    3's ``prototype_table_name`` (``citibike_weather_prototype_...``),
    so the original Stage 3 January 2025 table is preserved separately.
    """
    return f"citibike_weather_monthly_{year:04d}_{month:02d}"


def parse_year_month(year_raw: object, month_raw: object) -> Tuple[int, int]:
    """Parse raw CLI input into integers.

    Raises ``CliUsageError`` (a usage/input-shape problem) for anything
    that isn't a well-formed integer, or a month outside 1-12. Does NOT
    check availability against the source range -- that's
    ``parse_month_period``'s job, once the live range is known.
    """
    try:
        year = int(year_raw)
    except (TypeError, ValueError):
        raise CliUsageError(f"--year must be an integer, got {year_raw!r}") from None

    try:
        month = int(month_raw)
    except (TypeError, ValueError):
        raise CliUsageError(f"--month must be an integer, got {month_raw!r}") from None

    if not (1 <= month <= 12):
        raise CliUsageError(f"--month must be between 1 and 12, got {month}")

    return year, month


def compute_effective_range(
    citibike_min_date: date,
    citibike_max_date: date,
    weather_min_date: date,
    weather_max_date: date,
) -> Tuple[date, date]:
    """The shared range BOTH sources currently, actually cover.

    effective_min_date = max(the two minimum dates)
    effective_max_date = min(the two maximum dates)

    Always computed from live-fetched values -- never a hardcoded
    constant, and never derived from wall-clock "today" (the source
    table's most recent date can lag or lead the calendar date the
    pipeline happens to run on).
    """
    effective_min_date = max(citibike_min_date, weather_min_date)
    effective_max_date = min(citibike_max_date, weather_max_date)
    return effective_min_date, effective_max_date


def parse_month_period(
    year: int,
    month: int,
    effective_min_date: date,
    effective_max_date: date,
) -> MonthPeriod:
    """Build a ``MonthPeriod`` for an already-integer-parsed year/month,
    validated against the LIVE effective shared source range.

    Rejects PARTIAL months: valid only when the requested month's full
    start_date..end_date span lies entirely inside
    [effective_min_date, effective_max_date]. A month that only
    partially overlaps (e.g. the shared range ends mid-month) is
    rejected, not truncated.
    """
    rng = month_range(year, month)
    if rng.start_date < effective_min_date or rng.end_date > effective_max_date:
        raise InvalidMonthPeriodError(
            f"{year:04d}-{month:02d} ({rng.start_date}..{rng.end_date}) is not fully "
            f"contained in the current live shared source range "
            f"({effective_min_date}..{effective_max_date}); partial-month requests "
            f"are rejected, not truncated"
        )
    return MonthPeriod(year=year, month=month, start_date=rng.start_date, end_date=rng.end_date)


def load_destination_config(
    env: Optional[Mapping[str, str]] = None, default_project: Optional[str] = None
) -> Tuple[str, str]:
    """Read the destination project/dataset from the environment.

    Shared by both scripts/run_monthly_pipeline.py (Stage 4) and
    scripts/run_prototype_january_2025.py (Stage 3 compatibility
    wrapper) -- moved here from the original Stage 3 script so neither
    script needs to import the other.

    ``BQ_DESTINATION_DATASET`` is required and must name a dataset that
    already exists in the destination project -- this is never
    auto-created. ``BQ_DESTINATION_PROJECT_ID`` falls back to
    ``default_project`` (normally ``GCP_PROJECT_ID``) if unset.
    """
    source = os.environ if env is None else env

    destination_dataset = source.get("BQ_DESTINATION_DATASET")
    if not destination_dataset:
        raise ValueError(
            "BQ_DESTINATION_DATASET is required and must name an EXISTING "
            "dataset in your own project -- this script never creates one."
        )

    destination_project = source.get("BQ_DESTINATION_PROJECT_ID") or default_project
    if not destination_project:
        raise ValueError(
            "BQ_DESTINATION_PROJECT_ID or GCP_PROJECT_ID must be set to "
            "determine which project to write the destination table into."
        )

    return destination_project, destination_dataset
