"""Builds the Stage 6 analytics SQL from the existing monthly tables.

Pure string/data construction only -- no BigQuery SDK import, no I/O,
mirroring ``src.transformation.prototype_query``. Callers
(``src/loading/analytics_loader.py``, ``src/analytics/analytics_pipeline.py``)
are responsible for validating every monthly table ID with
``src.extraction.table_id.validate_table_id`` before the generated SQL
is ever executed -- table identifiers are interpolated into the SQL text
(BigQuery cannot parameterize a table reference), so that validation is
mandatory. This module does interpolate the IDs it is given but does not
re-validate them.

Design (see ``DECISIONS.md`` D-027..D-031):
  - ONE row per ``date``. The Stage 4/5 monthly tables are
    non-overlapping by construction, so a plain ``UNION ALL`` of them
    preserves one-row-per-date -- there is NO silent de-duplication. A
    duplicate ``date`` would indicate a real upstream problem and is
    caught by ``analytics_validation`` (rule A1), never hidden.
  - Columns are carried through UNCHANGED from the monthly output; the
    three dashboard-friendly derived fields (``temperature_band``,
    ``rain_category``, ``snow_category``) are computed ONCE over the
    union, from the carried columns.
  - Derived-field thresholds/labels live here as the single source of
    truth: the SQL ``CASE`` expressions are generated from the same
    constants the Python classifiers use, so the two can never drift
    (the unit tests assert they agree).
  - There is deliberately NO provenance/source_month column (owner
    decision -- removed from the approved design).
"""
from __future__ import annotations

from typing import List, Optional

# --- Destination naming ------------------------------------------------
# Deliberately NOT prefixed ``citibike_weather_monthly_`` so the analytics
# table can never be swept back into monthly-table discovery
# (``src.analytics.discovery``), and distinct from Stage 3's
# ``citibike_weather_prototype_`` naming.
ANALYTICS_TABLE_NAME = "citibike_weather_analytics"


def analytics_table_name() -> str:
    """The single, fixed Stage 6 destination table name.

    Fixed (not caller-supplied) so re-runs always overwrite the same
    table via ``CREATE OR REPLACE`` -- part of the idempotency contract
    (``DECISIONS.md`` D-030).
    """
    return ANALYTICS_TABLE_NAME


# --- Columns carried unchanged from the monthly output -----------------
# Every one of these exists in ``citibike_weather_monthly_YYYY_MM`` (the
# Stage 4 output shape -- see DATA_DICTIONARY.md 5b). ``date`` is first
# and is the grain key. This is the focused set needed to support all
# seven dashboard metrics plus the weather measures the derived bands are
# built from; the wider monthly column set (NYC/JC splits, classic/
# electric, medians, distance) is intentionally NOT carried to keep the
# analytics table minimal (``DECISIONS.md`` D-029).
CARRIED_COLUMNS: List[str] = [
    "date",
    "num_trips",
    "num_member_trips",
    "num_casual_trips",
    "avg_trip_duration_minutes",
    "weekday",
    "season",
    "tmin_f",
    "tmax_f",
    "tavg_f",
    "prcp_inches",
    "snow_inches",
    "is_rainy",
    "is_snowy",
    "weather_matched",
]

# The three derived columns appended after the carried columns.
DERIVED_COLUMNS: List[str] = ["temperature_band", "rain_category", "snow_category"]

# Full analytics table column order (carried + derived).
ANALYTICS_COLUMNS: List[str] = CARRIED_COLUMNS + DERIVED_COLUMNS


# --- Derived-field definitions (single source of truth) ----------------
# temperature_band: computed from tavg_f (degrees F). A NULL tavg_f
# (unmatched weather) maps to 'Unknown'. Boundaries are lower-inclusive /
# upper-exclusive; expressed here as an ordered upper-bound cascade
# applied AFTER the NULL check. The final band's bound is None (catch-all
# for the highest temperatures).
TEMPERATURE_BAND_UNKNOWN = "Unknown"
TEMPERATURE_BAND_CASCADE = [
    ("Freezing", 32.0),
    ("Cold", 50.0),
    ("Mild", 70.0),
    ("Warm", 85.0),
    ("Hot", None),
]
TEMPERATURE_BAND_VALUES: List[str] = [label for label, _ in TEMPERATURE_BAND_CASCADE] + [
    TEMPERATURE_BAND_UNKNOWN
]

# rain_category / snow_category: reuse the existing monthly is_rainy /
# is_snowy BOOL indicators (NOT re-thresholded from inches), so the
# categories can never diverge from the monthly definition. NULL (only
# possible for an unmatched-weather row) maps to 'Unknown'.
RAIN_CATEGORY_UNKNOWN = "Unknown"
RAIN_CATEGORY_TRUE = "Rainy"
RAIN_CATEGORY_FALSE = "Dry"
RAIN_CATEGORY_VALUES: List[str] = [RAIN_CATEGORY_TRUE, RAIN_CATEGORY_FALSE, RAIN_CATEGORY_UNKNOWN]

SNOW_CATEGORY_UNKNOWN = "Unknown"
SNOW_CATEGORY_TRUE = "Snowy"
SNOW_CATEGORY_FALSE = "No Snow"
SNOW_CATEGORY_VALUES: List[str] = [SNOW_CATEGORY_TRUE, SNOW_CATEGORY_FALSE, SNOW_CATEGORY_UNKNOWN]


def temperature_band(tavg_f: Optional[float]) -> str:
    """Python mirror of the ``temperature_band`` SQL ``CASE``.

    NULL -> 'Unknown'; otherwise the first cascade band whose
    upper-exclusive bound the value falls under. The unit tests assert
    this agrees with the generated SQL at every boundary.
    """
    if tavg_f is None:
        return TEMPERATURE_BAND_UNKNOWN
    for label, upper in TEMPERATURE_BAND_CASCADE:
        if upper is None or tavg_f < upper:
            return label
    return TEMPERATURE_BAND_UNKNOWN  # unreachable (final bound is None)


def rain_category(is_rainy: Optional[bool]) -> str:
    """Python mirror of the ``rain_category`` SQL ``CASE``."""
    if is_rainy is None:
        return RAIN_CATEGORY_UNKNOWN
    return RAIN_CATEGORY_TRUE if is_rainy else RAIN_CATEGORY_FALSE


def snow_category(is_snowy: Optional[bool]) -> str:
    """Python mirror of the ``snow_category`` SQL ``CASE``."""
    if is_snowy is None:
        return SNOW_CATEGORY_UNKNOWN
    return SNOW_CATEGORY_TRUE if is_snowy else SNOW_CATEGORY_FALSE


def _temperature_band_case(column: str = "tavg_f") -> str:
    """Generate the ``temperature_band`` CASE from ``TEMPERATURE_BAND_CASCADE``."""
    lines = ["CASE", f"    WHEN {column} IS NULL THEN '{TEMPERATURE_BAND_UNKNOWN}'"]
    for label, upper in TEMPERATURE_BAND_CASCADE:
        if upper is None:
            lines.append(f"    ELSE '{label}'")
        else:
            lines.append(f"    WHEN {column} < {upper} THEN '{label}'")
    lines.append("  END AS temperature_band")
    return "\n  ".join(lines)


def _rain_category_case(column: str = "is_rainy") -> str:
    return (
        "CASE\n"
        f"    WHEN {column} IS NULL THEN '{RAIN_CATEGORY_UNKNOWN}'\n"
        f"    WHEN {column} THEN '{RAIN_CATEGORY_TRUE}'\n"
        f"    ELSE '{RAIN_CATEGORY_FALSE}'\n"
        "  END AS rain_category"
    )


def _snow_category_case(column: str = "is_snowy") -> str:
    return (
        "CASE\n"
        f"    WHEN {column} IS NULL THEN '{SNOW_CATEGORY_UNKNOWN}'\n"
        f"    WHEN {column} THEN '{SNOW_CATEGORY_TRUE}'\n"
        f"    ELSE '{SNOW_CATEGORY_FALSE}'\n"
        "  END AS snow_category"
    )


def _carried_select_list(indent: str = "    ") -> str:
    return (",\n" + indent).join(CARRIED_COLUMNS)


def build_union_select(monthly_table_ids: List[str]) -> str:
    """Build a ``UNION ALL`` over the carried columns of every monthly
    table -- the raw daily-grain combination WITHOUT the derived fields.

    Used both as the inner ``combined`` relation of the analytics CTAS
    (``build_analytics_select``) and, standalone, as the source relation
    for the preservation aggregates in ``analytics_validation`` (so the
    analytics table is reconciled against exactly the rows it was built
    from).

    ``monthly_table_ids`` must be a non-empty list of already-validated,
    fully-qualified ``project.dataset.table`` strings.
    """
    if not monthly_table_ids:
        raise ValueError("build_union_select requires at least one monthly table id")

    select_list = _carried_select_list()
    blocks = [f"SELECT\n    {select_list}\n  FROM `{tid}`" for tid in monthly_table_ids]
    return "\n  UNION ALL\n  ".join(blocks)


def build_analytics_select(monthly_table_ids: List[str]) -> str:
    """Build the full Stage 6 analytics ``SELECT`` (carried columns +
    the three derived fields), one row per date, ordered by date.

    This is the ``AS SELECT`` body the loader wraps in
    ``CREATE OR REPLACE TABLE``. Column lists are explicit (no
    ``SELECT *``). ``monthly_table_ids`` must already be validated.
    """
    union_sql = build_union_select(monthly_table_ids)
    outer_carried = _carried_select_list("  ")
    return (
        "WITH combined AS (\n"
        f"  {union_sql}\n"
        ")\n"
        "SELECT\n"
        f"  {outer_carried},\n"
        f"  {_temperature_band_case()},\n"
        f"  {_rain_category_case()},\n"
        f"  {_snow_category_case()}\n"
        "FROM combined\n"
        "ORDER BY date"
    )
