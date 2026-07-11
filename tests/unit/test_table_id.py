import pytest
from google.cloud import bigquery

from src.extraction.table_id import validate_table_id


def test_accepts_real_citibike_table_id():
    ref = validate_table_id("nyu-datasets.citibike.m_daily_trips")
    assert isinstance(ref, bigquery.TableReference)
    assert ref.project == "nyu-datasets"
    assert ref.dataset_id == "citibike"
    assert ref.table_id == "m_daily_trips"


def test_accepts_real_weather_table_id():
    ref = validate_table_id("nyu-datasets.weather.m_weather_daily_nyc")
    assert ref.project == "nyu-datasets"
    assert ref.dataset_id == "weather"
    assert ref.table_id == "m_weather_daily_nyc"


def test_rejects_hyphen_in_dataset_segment():
    with pytest.raises(ValueError, match="dataset"):
        validate_table_id("nyu-datasets.city-bike.m_daily_trips")


@pytest.mark.parametrize(
    "bad_id",
    [
        "nyu-datasets.citibike.m_daily_trips; DROP TABLE x",
        "nyu-datasets.citibike.`m_daily_trips`",
        "nyu-datasets.citibike.'m_daily_trips'",
        "nyu-datasets.citibike.m daily trips",
        'nyu-datasets.citibike.m_daily_trips"',
    ],
)
def test_rejects_unsafe_characters(bad_id):
    with pytest.raises(ValueError):
        validate_table_id(bad_id)


def test_rejects_wrong_number_of_segments():
    with pytest.raises(ValueError):
        validate_table_id("nyu-datasets.citibike")

    with pytest.raises(ValueError):
        validate_table_id("nyu-datasets.citibike.m_daily_trips.extra")


def test_rejects_empty_or_non_string():
    with pytest.raises(ValueError):
        validate_table_id("")

    with pytest.raises(ValueError):
        validate_table_id(None)  # type: ignore[arg-type]
