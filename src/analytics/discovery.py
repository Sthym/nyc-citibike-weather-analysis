"""Discovery of the Stage 4/5 monthly destination tables to combine.

Stage 6 reads the EXISTING monthly destination tables
(``citibike_weather_monthly_YYYY_MM``) in the caller's own destination
dataset -- never the raw public source files, and never a BigQuery
wildcard (which could accidentally sweep in the analytics table or any
unrelated table). The list is built explicitly and deterministically.

The pure selection/filtering/ordering logic (``select_monthly_table_ids``,
``parse_monthly_table_name``, ``missing_months_in_range``) has no I/O and
no BigQuery SDK import, so it is fully unit-testable with a plain list of
table names -- the same pure-core / thin-I/O split used across this
project. ``list_dataset_table_names`` is the only function that touches a
live client, and ``discover_monthly_tables`` composes the two.
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

from src.extraction.table_id import validate_table_id

# Matches EXACTLY the Stage 4 monthly naming
# (``src.pipeline.month_period.monthly_table_name``): the analytics table
# (``citibike_weather_analytics``) and the Stage 3 prototype tables
# (``citibike_weather_prototype_YYYY_MM``) deliberately do NOT match, so
# they are never combined into the analytics output.
MONTHLY_TABLE_RE = re.compile(r"^citibike_weather_monthly_(\d{4})_(\d{2})$")

YearMonth = Tuple[int, int]


class NoMonthlyTablesError(ValueError):
    """Raised when discovery finds zero monthly tables to combine.

    Distinct from a config/auth problem: the dataset was reachable, it
    simply contains no ``citibike_weather_monthly_YYYY_MM`` tables (or
    none within a requested ``--start``/``--end`` window). The pipeline
    maps this to a distinct exit code (see ``analytics_pipeline``).
    """


def parse_monthly_table_name(name: str) -> Optional[YearMonth]:
    """Return ``(year, month)`` if ``name`` is a monthly table name, else
    ``None``. ``month`` outside 1-12 is rejected (returns ``None``)."""
    match = MONTHLY_TABLE_RE.match(name)
    if not match:
        return None
    year, month = int(match.group(1)), int(match.group(2))
    if not (1 <= month <= 12):
        return None
    return year, month


def _in_range(ym: YearMonth, start: Optional[YearMonth], end: Optional[YearMonth]) -> bool:
    if start is not None and ym < start:
        return False
    if end is not None and ym > end:
        return False
    return True


def missing_months_in_range(
    present: List[YearMonth], start: YearMonth, end: YearMonth
) -> List[YearMonth]:
    """Every ``(year, month)`` from ``start`` to ``end`` inclusive that is
    NOT in ``present``, in chronological order.

    Only meaningful when an explicit range is requested; used to WARN
    (never to fail) about months the user asked for that have no monthly
    table yet -- the analytics table is still built from whatever IS
    available.
    """
    present_set = set(present)
    missing: List[YearMonth] = []
    year, month = start
    while (year, month) <= end:
        if (year, month) not in present_set:
            missing.append((year, month))
        month += 1
        if month == 13:
            month = 1
            year += 1
    return missing


def select_monthly_table_ids(
    project: str,
    dataset: str,
    table_names: List[str],
    start: Optional[YearMonth] = None,
    end: Optional[YearMonth] = None,
) -> List[str]:
    """Filter ``table_names`` to the monthly tables, optionally restrict to
    a ``[start, end]`` (year, month) window, sort chronologically, and
    return fully-qualified, VALIDATED ``project.dataset.table`` ids.

    Every returned id is passed through
    ``src.extraction.table_id.validate_table_id`` (defense in depth,
    even though these names came from a listing rather than user input).
    Raises ``NoMonthlyTablesError`` if nothing matches.
    """
    matched: List[Tuple[YearMonth, str]] = []
    for name in table_names:
        ym = parse_monthly_table_name(name)
        if ym is None:
            continue
        if not _in_range(ym, start, end):
            continue
        matched.append((ym, name))

    matched.sort(key=lambda pair: pair[0])

    if not matched:
        window = ""
        if start is not None or end is not None:
            window = f" within requested window {start}..{end}"
        raise NoMonthlyTablesError(
            f"no citibike_weather_monthly_YYYY_MM tables found in "
            f"{project}.{dataset}{window}; nothing to combine"
        )

    table_ids: List[str] = []
    for _ym, name in matched:
        table_id = f"{project}.{dataset}.{name}"
        validate_table_id(table_id)  # raises ValueError on anything unsafe/malformed
        table_ids.append(table_id)
    return table_ids


def list_dataset_table_names(client, project: str, dataset: str) -> List[str]:
    """Return the bare table names in ``project.dataset`` via the live
    client (the only I/O in this module).

    ``client`` is any object exposing ``list_tables(dataset_ref)`` that
    yields items with a ``table_id`` attribute -- a real
    ``google.cloud.bigquery.Client`` in production, a fake in tests.
    """
    dataset_ref = f"{project}.{dataset}"
    return [table.table_id for table in client.list_tables(dataset_ref)]


def discover_monthly_tables(
    client,
    project: str,
    dataset: str,
    start: Optional[YearMonth] = None,
    end: Optional[YearMonth] = None,
) -> List[str]:
    """List ``project.dataset``, then select/validate/order the monthly
    tables. Raises ``NoMonthlyTablesError`` if none are found."""
    names = list_dataset_table_names(client, project, dataset)
    return select_monthly_table_ids(project, dataset, names, start=start, end=end)
