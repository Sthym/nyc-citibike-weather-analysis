"""Unit tests for src/analytics/analytics_query.py -- pure, no I/O."""
import pytest

from src.analytics import analytics_query as aq


MONTHLY_IDS = [
    "proj.ds.citibike_weather_monthly_2025_01",
    "proj.ds.citibike_weather_monthly_2025_02",
]


class TestNaming:
    def test_analytics_table_name_is_fixed(self):
        assert aq.analytics_table_name() == "citibike_weather_analytics"

    def test_analytics_name_is_not_a_monthly_name(self):
        # Must not be swept back into monthly-table discovery.
        assert not aq.analytics_table_name().startswith("citibike_weather_monthly_")

    def test_column_order_is_carried_then_derived(self):
        assert aq.ANALYTICS_COLUMNS == aq.CARRIED_COLUMNS + aq.DERIVED_COLUMNS
        assert aq.CARRIED_COLUMNS[0] == "date"
        assert aq.DERIVED_COLUMNS == ["temperature_band", "rain_category", "snow_category"]


class TestTemperatureBand:
    @pytest.mark.parametrize(
        "value,expected",
        [
            (None, "Unknown"),
            (-5.0, "Freezing"),
            (31.9, "Freezing"),
            (32.0, "Cold"),
            (49.9, "Cold"),
            (50.0, "Mild"),
            (69.9, "Mild"),
            (70.0, "Warm"),
            (84.9, "Warm"),
            (85.0, "Hot"),
            (120.0, "Hot"),
        ],
    )
    def test_boundaries(self, value, expected):
        assert aq.temperature_band(value) == expected

    def test_values_set_matches_cascade(self):
        assert aq.TEMPERATURE_BAND_VALUES == ["Freezing", "Cold", "Mild", "Warm", "Hot", "Unknown"]


class TestRainSnowCategory:
    @pytest.mark.parametrize(
        "value,expected", [(None, "Unknown"), (True, "Rainy"), (False, "Dry")]
    )
    def test_rain(self, value, expected):
        assert aq.rain_category(value) == expected

    @pytest.mark.parametrize(
        "value,expected", [(None, "Unknown"), (True, "Snowy"), (False, "No Snow")]
    )
    def test_snow(self, value, expected):
        assert aq.snow_category(value) == expected


class TestBuildUnionSelect:
    def test_empty_raises(self):
        with pytest.raises(ValueError):
            aq.build_union_select([])

    def test_union_all_between_every_table(self):
        sql = aq.build_union_select(MONTHLY_IDS)
        assert sql.count("UNION ALL") == len(MONTHLY_IDS) - 1
        for tid in MONTHLY_IDS:
            assert f"`{tid}`" in sql

    def test_projects_exactly_the_carried_columns_no_derived(self):
        sql = aq.build_union_select(MONTHLY_IDS[:1])
        for col in aq.CARRIED_COLUMNS:
            assert col in sql
        # Derived fields are added ONCE over the union, not per-table.
        assert "temperature_band" not in sql


class TestBuildAnalyticsSelect:
    def test_empty_raises(self):
        with pytest.raises(ValueError):
            aq.build_analytics_select([])

    def test_has_cte_union_derived_and_order_by(self):
        sql = aq.build_analytics_select(MONTHLY_IDS)
        assert sql.startswith("WITH combined AS (")
        assert "UNION ALL" in sql
        assert "AS temperature_band" in sql
        assert "AS rain_category" in sql
        assert "AS snow_category" in sql
        assert sql.rstrip().endswith("ORDER BY date")

    def test_no_source_month_anywhere(self):
        sql = aq.build_analytics_select(MONTHLY_IDS)
        assert "source_month" not in sql

    def test_no_select_star(self):
        sql = aq.build_analytics_select(MONTHLY_IDS)
        assert "SELECT *" not in sql

    def test_temperature_band_sql_matches_cascade_thresholds(self):
        sql = aq.build_analytics_select(MONTHLY_IDS[:1])
        # The generated CASE must reflect the same thresholds the Python
        # classifier uses (single source of truth -> no drift).
        assert "WHEN tavg_f IS NULL THEN 'Unknown'" in sql
        for label, upper in aq.TEMPERATURE_BAND_CASCADE:
            if upper is None:
                assert f"ELSE '{label}'" in sql
            else:
                assert f"WHEN tavg_f < {upper} THEN '{label}'" in sql

    def test_rain_and_snow_reuse_indicator_columns(self):
        sql = aq.build_analytics_select(MONTHLY_IDS[:1])
        assert "WHEN is_rainy THEN 'Rainy'" in sql
        assert "WHEN is_snowy THEN 'Snowy'" in sql
        assert "ELSE 'No Snow'" in sql
