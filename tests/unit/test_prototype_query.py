from datetime import date

import pytest

from src.transformation.prototype_query import (
    CITIBIKE_COLUMNS,
    WEATHER_COLUMNS,
    build_prototype_query,
    month_range,
)


class TestMonthRange:
    def test_january_2025(self):
        rng = month_range(2025, 1)
        assert rng.start_date == date(2025, 1, 1)
        assert rng.end_date == date(2025, 1, 31)

    def test_february_leap_year(self):
        rng = month_range(2024, 2)
        assert rng.start_date == date(2024, 2, 1)
        assert rng.end_date == date(2024, 2, 29)

    def test_february_non_leap_year(self):
        rng = month_range(2025, 2)
        assert rng.end_date == date(2025, 2, 28)

    def test_thirty_day_month(self):
        rng = month_range(2025, 4)
        assert rng.end_date == date(2025, 4, 30)


class TestBuildPrototypeQuery:
    def setup_method(self):
        self.sql = build_prototype_query(
            "nyu-datasets.citibike.m_daily_trips",
            "nyu-datasets.weather.m_weather_daily_nyc",
        )

    def test_uses_query_parameters_not_literals(self):
        assert "@start_date" in self.sql
        assert "@end_date" in self.sql
        # No hardcoded date literal anywhere in the generated SQL.
        assert "2025-01" not in self.sql

    def test_includes_full_citibike_column_list(self):
        for column in CITIBIKE_COLUMNS:
            assert f"c.{column}" in self.sql or column in self.sql

    def test_does_not_use_wildcard_select(self):
        assert "c.*" not in self.sql
        assert "w.*" not in self.sql
        assert "SELECT *" not in self.sql

    def test_includes_curated_weather_columns(self):
        for column in WEATHER_COLUMNS:
            assert column in self.sql

    def test_casts_indicator_columns_to_bool(self):
        assert "CAST(w.is_rainy AS BOOL)" in self.sql
        assert "CAST(w.is_snowy AS BOOL)" in self.sql

    def test_includes_weather_matched_flag(self):
        assert "weather_matched" in self.sql
        assert "(w.date IS NOT NULL) AS weather_matched" in self.sql

    def test_includes_weekday_derivation(self):
        assert "FORMAT_DATE('%A', c.date) AS weekday" in self.sql

    def test_left_join_on_date(self):
        assert "LEFT JOIN weather_month AS w" in self.sql
        assert "ON c.date = w.date" in self.sql

    def test_interpolates_source_table_ids(self):
        assert "nyu-datasets.citibike.m_daily_trips" in self.sql
        assert "nyu-datasets.weather.m_weather_daily_nyc" in self.sql

    def test_filters_both_ctes_by_date_range(self):
        assert self.sql.count("WHERE date BETWEEN @start_date AND @end_date") == 2
