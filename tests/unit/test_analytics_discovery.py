"""Unit tests for src/analytics/discovery.py -- pure selection logic plus
a fake-client I/O path. No network access."""
import pytest

from src.analytics import discovery


class FakeTable:
    def __init__(self, table_id):
        self.table_id = table_id


class FakeListClient:
    def __init__(self, names, raise_exc=None):
        self._names = names
        self.raise_exc = raise_exc
        self.calls = []

    def list_tables(self, dataset_ref):
        self.calls.append(dataset_ref)
        if self.raise_exc:
            raise self.raise_exc
        return [FakeTable(n) for n in self._names]


class TestParseMonthlyTableName:
    def test_valid(self):
        assert discovery.parse_monthly_table_name("citibike_weather_monthly_2025_01") == (2025, 1)

    def test_month_out_of_range_is_none(self):
        assert discovery.parse_monthly_table_name("citibike_weather_monthly_2025_13") is None

    @pytest.mark.parametrize(
        "name",
        [
            "citibike_weather_analytics",
            "citibike_weather_prototype_2025_01",
            "citibike_weather_monthly_2025",
            "citibike_weather_monthly_2025_1",
            "some_other_table",
        ],
    )
    def test_non_monthly_names_are_none(self, name):
        assert discovery.parse_monthly_table_name(name) is None


class TestSelectMonthlyTableIds:
    def test_filters_sorts_and_qualifies(self):
        names = [
            "citibike_weather_monthly_2025_02",
            "citibike_weather_analytics",  # excluded
            "citibike_weather_monthly_2025_01",
            "citibike_weather_prototype_2025_01",  # excluded
            "unrelated",  # excluded
        ]
        ids = discovery.select_monthly_table_ids("proj", "ds", names)
        assert ids == [
            "proj.ds.citibike_weather_monthly_2025_01",
            "proj.ds.citibike_weather_monthly_2025_02",
        ]

    def test_sorts_across_year_boundary(self):
        names = [
            "citibike_weather_monthly_2025_01",
            "citibike_weather_monthly_2024_12",
        ]
        ids = discovery.select_monthly_table_ids("p", "d", names)
        assert ids == [
            "p.d.citibike_weather_monthly_2024_12",
            "p.d.citibike_weather_monthly_2025_01",
        ]

    def test_empty_raises_no_monthly_tables(self):
        with pytest.raises(discovery.NoMonthlyTablesError):
            discovery.select_monthly_table_ids("p", "d", ["citibike_weather_analytics"])

    def test_range_filter_inclusive(self):
        names = [f"citibike_weather_monthly_2025_{m:02d}" for m in range(1, 7)]
        ids = discovery.select_monthly_table_ids("p", "d", names, start=(2025, 2), end=(2025, 4))
        assert ids == [
            "p.d.citibike_weather_monthly_2025_02",
            "p.d.citibike_weather_monthly_2025_03",
            "p.d.citibike_weather_monthly_2025_04",
        ]

    def test_range_with_no_match_raises(self):
        names = ["citibike_weather_monthly_2025_01"]
        with pytest.raises(discovery.NoMonthlyTablesError):
            discovery.select_monthly_table_ids("p", "d", names, start=(2026, 1), end=(2026, 12))


class TestMissingMonthsInRange:
    def test_reports_gaps_in_order(self):
        present = [(2025, 1), (2025, 3)]
        missing = discovery.missing_months_in_range(present, (2025, 1), (2025, 4))
        assert missing == [(2025, 2), (2025, 4)]

    def test_none_missing(self):
        present = [(2025, 1), (2025, 2)]
        assert discovery.missing_months_in_range(present, (2025, 1), (2025, 2)) == []


class TestDiscoverMonthlyTables:
    def test_happy_path(self):
        client = FakeListClient(
            ["citibike_weather_monthly_2025_01", "citibike_weather_monthly_2025_02"]
        )
        ids = discovery.discover_monthly_tables(client, "proj", "ds")
        assert ids == [
            "proj.ds.citibike_weather_monthly_2025_01",
            "proj.ds.citibike_weather_monthly_2025_02",
        ]
        assert client.calls == ["proj.ds"]

    def test_none_found_raises(self):
        client = FakeListClient(["citibike_weather_analytics"])
        with pytest.raises(discovery.NoMonthlyTablesError):
            discovery.discover_monthly_tables(client, "proj", "ds")
