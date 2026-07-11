from datetime import date

import pytest

from src.loading.prototype_loader import PrototypeLoader, prototype_table_name


class FakeQueryJob:
    def __init__(self):
        self.result_called = False

    def result(self):
        self.result_called = True
        return []


class FakeClient:
    """Records every call to `.query()` without touching the network."""

    def __init__(self):
        self.calls = []
        self._job = FakeQueryJob()

    def query(self, sql, job_config=None, location=None):
        self.calls.append({"sql": sql, "job_config": job_config, "location": location})
        return self._job


class TestPrototypeTableName:
    def test_derives_name_from_year_and_month(self):
        assert prototype_table_name(2025, 1) == "citibike_weather_prototype_2025_01"

    def test_zero_pads_single_digit_month(self):
        assert prototype_table_name(2025, 9) == "citibike_weather_prototype_2025_09"


class TestBuildLoadDdl:
    def test_uses_create_or_replace_table(self):
        loader = PrototypeLoader(project="my-billing-project", client=FakeClient())
        ddl = loader.build_load_ddl(
            destination_project="my-billing-project",
            destination_dataset="my_dataset",
            year=2025,
            month=1,
            citibike_table="nyu-datasets.citibike.m_daily_trips",
            weather_table="nyu-datasets.weather.m_weather_daily_nyc",
        )
        assert ddl.startswith("CREATE OR REPLACE TABLE")
        assert "`my-billing-project.my_dataset.citibike_weather_prototype_2025_01`" in ddl

    def test_ddl_has_no_embedded_date_literals(self):
        loader = PrototypeLoader(project="my-billing-project", client=FakeClient())
        ddl = loader.build_load_ddl(
            destination_project="my-billing-project",
            destination_dataset="my_dataset",
            year=2025,
            month=1,
            citibike_table="nyu-datasets.citibike.m_daily_trips",
            weather_table="nyu-datasets.weather.m_weather_daily_nyc",
        )
        assert "@start_date" in ddl
        assert "@end_date" in ddl

    def test_rejects_invalid_source_table_id(self):
        loader = PrototypeLoader(project="my-billing-project", client=FakeClient())
        with pytest.raises(ValueError):
            loader.build_load_ddl(
                destination_project="my-billing-project",
                destination_dataset="my_dataset",
                year=2025,
                month=1,
                citibike_table="not a valid table id",
                weather_table="nyu-datasets.weather.m_weather_daily_nyc",
            )

    def test_rejects_invalid_destination(self):
        loader = PrototypeLoader(project="my-billing-project", client=FakeClient())
        with pytest.raises(ValueError):
            loader.build_load_ddl(
                destination_project="my-billing-project",
                destination_dataset="bad dataset name",
                year=2025,
                month=1,
                citibike_table="nyu-datasets.citibike.m_daily_trips",
                weather_table="nyu-datasets.weather.m_weather_daily_nyc",
            )


class TestLoad:
    def test_binds_start_and_end_date_as_query_parameters(self):
        fake_client = FakeClient()
        loader = PrototypeLoader(project="my-billing-project", client=fake_client)
        loader.load(
            destination_project="my-billing-project",
            destination_dataset="my_dataset",
            year=2025,
            month=1,
            citibike_table="nyu-datasets.citibike.m_daily_trips",
            weather_table="nyu-datasets.weather.m_weather_daily_nyc",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
        )
        assert len(fake_client.calls) == 1
        job_config = fake_client.calls[0]["job_config"]
        param_names = {p.name for p in job_config.query_parameters}
        assert param_names == {"start_date", "end_date"}

    def test_waits_for_query_job_completion(self):
        fake_client = FakeClient()
        loader = PrototypeLoader(project="my-billing-project", client=fake_client)
        loader.load(
            destination_project="my-billing-project",
            destination_dataset="my_dataset",
            year=2025,
            month=1,
            citibike_table="nyu-datasets.citibike.m_daily_trips",
            weather_table="nyu-datasets.weather.m_weather_daily_nyc",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
        )
        assert fake_client._job.result_called is True

    def test_returns_destination_table_reference(self):
        fake_client = FakeClient()
        loader = PrototypeLoader(project="my-billing-project", client=fake_client)
        ref = loader.load(
            destination_project="my-billing-project",
            destination_dataset="my_dataset",
            year=2025,
            month=1,
            citibike_table="nyu-datasets.citibike.m_daily_trips",
            weather_table="nyu-datasets.weather.m_weather_daily_nyc",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
        )
        assert ref.project == "my-billing-project"
        assert ref.dataset_id == "my_dataset"
        assert ref.table_id == "citibike_weather_prototype_2025_01"

    def test_passes_query_location(self):
        fake_client = FakeClient()
        loader = PrototypeLoader(project="my-billing-project", location="US", client=fake_client)
        loader.load(
            destination_project="my-billing-project",
            destination_dataset="my_dataset",
            year=2025,
            month=1,
            citibike_table="nyu-datasets.citibike.m_daily_trips",
            weather_table="nyu-datasets.weather.m_weather_daily_nyc",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
        )
        assert fake_client.calls[0]["location"] == "US"

    def test_no_default_destination_dataset_required_explicitly(self):
        # There is no signature default for destination_dataset -- calling
        # without it must fail at the Python level, proving no silent
        # auto-creation / implicit destination is possible.
        loader = PrototypeLoader(project="my-billing-project", client=FakeClient())
        with pytest.raises(TypeError):
            loader.load(
                destination_project="my-billing-project",
                year=2025,
                month=1,
                citibike_table="nyu-datasets.citibike.m_daily_trips",
                weather_table="nyu-datasets.weather.m_weather_daily_nyc",
                start_date=date(2025, 1, 1),
                end_date=date(2025, 1, 31),
            )


class TestTableNameOverride:
    """Stage 4 addition: an explicit table_name overrides the derived
    Stage 3 prototype_table_name(year, month), so callers with a
    different naming convention (e.g. Stage 4's
    citibike_weather_monthly_YYYY_MM) can reuse this loader unchanged.
    """

    def test_build_load_ddl_uses_override_when_given(self):
        loader = PrototypeLoader(project="my-billing-project", client=FakeClient())
        ddl = loader.build_load_ddl(
            destination_project="my-billing-project",
            destination_dataset="my_dataset",
            year=2025,
            month=2,
            citibike_table="nyu-datasets.citibike.m_daily_trips",
            weather_table="nyu-datasets.weather.m_weather_daily_nyc",
            table_name="citibike_weather_monthly_2025_02",
        )
        assert "`my-billing-project.my_dataset.citibike_weather_monthly_2025_02`" in ddl
        assert "prototype" not in ddl

    def test_build_load_ddl_falls_back_to_derived_name_when_omitted(self):
        loader = PrototypeLoader(project="my-billing-project", client=FakeClient())
        ddl = loader.build_load_ddl(
            destination_project="my-billing-project",
            destination_dataset="my_dataset",
            year=2025,
            month=1,
            citibike_table="nyu-datasets.citibike.m_daily_trips",
            weather_table="nyu-datasets.weather.m_weather_daily_nyc",
        )
        assert "`my-billing-project.my_dataset.citibike_weather_prototype_2025_01`" in ddl

    def test_load_uses_override_and_returns_matching_reference(self):
        fake_client = FakeClient()
        loader = PrototypeLoader(project="my-billing-project", client=fake_client)
        ref = loader.load(
            destination_project="my-billing-project",
            destination_dataset="my_dataset",
            year=2025,
            month=2,
            citibike_table="nyu-datasets.citibike.m_daily_trips",
            weather_table="nyu-datasets.weather.m_weather_daily_nyc",
            start_date=date(2025, 2, 1),
            end_date=date(2025, 2, 28),
            table_name="citibike_weather_monthly_2025_02",
        )
        assert ref.table_id == "citibike_weather_monthly_2025_02"

    def test_load_default_behavior_unchanged_when_override_omitted(self):
        fake_client = FakeClient()
        loader = PrototypeLoader(project="my-billing-project", client=fake_client)
        ref = loader.load(
            destination_project="my-billing-project",
            destination_dataset="my_dataset",
            year=2025,
            month=1,
            citibike_table="nyu-datasets.citibike.m_daily_trips",
            weather_table="nyu-datasets.weather.m_weather_daily_nyc",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
        )
        assert ref.table_id == "citibike_weather_prototype_2025_01"
