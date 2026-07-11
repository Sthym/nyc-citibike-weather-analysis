import pytest

from src.extraction.config import (
    DEFAULT_BQ_LOCATION,
    DEFAULT_CITIBIKE_TABLE,
    DEFAULT_WEATHER_TABLE,
    load_config,
)


def test_loads_project_id_from_env():
    config = load_config({"GCP_PROJECT_ID": "my-billing-project"})
    assert config.gcp_project_id == "my-billing-project"


def test_raises_if_project_id_missing():
    with pytest.raises(ValueError, match="GCP_PROJECT_ID"):
        load_config({})


def test_citibike_table_defaults_when_env_unset():
    config = load_config({"GCP_PROJECT_ID": "p"})
    assert config.citibike_table == DEFAULT_CITIBIKE_TABLE


def test_weather_table_defaults_when_env_unset():
    config = load_config({"GCP_PROJECT_ID": "p"})
    assert config.weather_table == DEFAULT_WEATHER_TABLE


def test_env_override_replaces_default_citibike_table():
    # Project segments may contain hyphens; dataset/table segments may not
    # (see src/extraction/table_id.py) -- this fixture respects both rules.
    config = load_config(
        {
            "GCP_PROJECT_ID": "p",
            "BQ_CITIBIKE_TABLE": "other-proj.other_ds.other_table",
        }
    )
    assert config.citibike_table == "other-proj.other_ds.other_table"


def test_bq_location_defaults_to_us():
    config = load_config({"GCP_PROJECT_ID": "p"})
    assert config.bq_location == DEFAULT_BQ_LOCATION == "US"


def test_bq_location_overridden_via_env():
    config = load_config({"GCP_PROJECT_ID": "p", "BQ_LOCATION": "EU"})
    assert config.bq_location == "EU"


def test_rejects_malformed_table_id_at_load():
    with pytest.raises(ValueError):
        load_config({"GCP_PROJECT_ID": "p", "BQ_CITIBIKE_TABLE": "bad-id-no-dots"})


def test_rejects_hyphenated_dataset_at_load():
    with pytest.raises(ValueError):
        load_config(
            {
                "GCP_PROJECT_ID": "p",
                "BQ_CITIBIKE_TABLE": "nyu-datasets.city-bike.m_daily_trips",
            }
        )
