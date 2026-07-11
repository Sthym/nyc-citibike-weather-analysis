"""Builds the parameterized Stage 3 one-month prototype join query.

Pure string/data construction only -- no BigQuery SDK import, no I/O.
Callers (src/loading/prototype_loader.py, scripts/) are responsible for:
  1. Validating both source table IDs with
     ``src.extraction.table_id.validate_table_id`` before calling
     ``build_prototype_query`` -- this module does not re-validate them.
  2. Binding ``@start_date`` / ``@end_date`` as real BigQuery query
     parameters (``bigquery.ScalarQueryParameter``) when the query
     actually runs. The date range is never interpolated into the SQL
     text as a literal.

Table identifiers themselves (``citibike_table`` / ``weather_table``)
are still interpolated directly into the SQL text -- BigQuery does not
support parameterizing table references, only scalar/array values used
in expressions such as a WHERE clause. That is why table-ID validation
(character allow-list + BigQuery's own parser) is mandatory before this
function is ever called.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date

# The complete, verified 15-column Citi Bike daily shape (Section 1a,
# DATA_DICTIONARY.md). Kept in full -- no c.* / EXCEPT(date).
CITIBIKE_COLUMNS = [
    "date",
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
    "avg_trip_duration_minutes",
    "median_trip_duration_minutes",
    "avg_distance_meters",
]

# The curated 8 weather fields approved for the prototype (Stage 3
# design). is_rainy/is_snowy are source INT64 0/1 indicators, cast to
# BOOL here at selection time.
WEATHER_COLUMNS = [
    "tmin_f",
    "tmax_f",
    "tavg_f",
    "prcp_inches",
    "is_rainy",
    "snow_inches",
    "is_snowy",
    "season",
]


@dataclass(frozen=True)
class MonthRange:
    start_date: date
    end_date: date


def month_range(year: int, month: int) -> MonthRange:
    """Return the first and last calendar date of the given month."""
    last_day = calendar.monthrange(year, month)[1]
    return MonthRange(
        start_date=date(year, month, 1),
        end_date=date(year, month, last_day),
    )


_CITIBIKE_SELECT_LIST = ",\n    ".join(CITIBIKE_COLUMNS)
_WEATHER_SELECT_LIST = ",\n    ".join(
    col for col in WEATHER_COLUMNS if col not in ("is_rainy", "is_snowy")
)

PROTOTYPE_QUERY_TEMPLATE = """\
WITH citibike_month AS (
  SELECT
    {citibike_columns}
  FROM `{citibike_table}`
  WHERE date BETWEEN @start_date AND @end_date
),
weather_month AS (
  SELECT
    {weather_columns},
    is_rainy,
    is_snowy
  FROM `{weather_table}`
  WHERE date BETWEEN @start_date AND @end_date
)
SELECT
  {citibike_select},
  FORMAT_DATE('%A', c.date) AS weekday,
  {weather_select},
  CAST(w.is_rainy AS BOOL) AS is_rainy,
  CAST(w.is_snowy AS BOOL) AS is_snowy,
  (w.date IS NOT NULL) AS weather_matched
FROM citibike_month AS c
LEFT JOIN weather_month AS w
  ON c.date = w.date
"""


def build_prototype_query(citibike_table: str, weather_table: str) -> str:
    """Build the Stage 3 prototype join SQL.

    ``@start_date`` and ``@end_date`` are left as BigQuery query
    parameter placeholders -- never interpolated as literals. Both
    table arguments must already be validated, fully-qualified
    ``project.dataset.table`` strings (see module docstring).
    """
    citibike_select = ",\n  ".join(f"c.{col}" for col in CITIBIKE_COLUMNS)
    weather_select = ",\n  ".join(
        f"w.{col}" for col in WEATHER_COLUMNS if col not in ("is_rainy", "is_snowy")
    )
    return PROTOTYPE_QUERY_TEMPLATE.format(
        citibike_table=citibike_table,
        weather_table=weather_table,
        citibike_columns=_CITIBIKE_SELECT_LIST,
        weather_columns=_WEATHER_SELECT_LIST,
        citibike_select=citibike_select,
        weather_select=weather_select,
    )
