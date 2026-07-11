"""Environment-driven configuration for the Stage 2 extraction foundation.

No credentials and no personal GCP project ID are ever hardcoded here.
Only the two source-table IDs (which name a shared, non-secret teaching
dataset) and a default query location have built-in defaults.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping, Optional

from .table_id import validate_table_id

DEFAULT_CITIBIKE_TABLE = "nyu-datasets.citibike.m_daily_trips"
DEFAULT_WEATHER_TABLE = "nyu-datasets.weather.m_weather_daily_nyc"
DEFAULT_BQ_LOCATION = "US"


@dataclass(frozen=True)
class Config:
    gcp_project_id: str
    citibike_table: str
    weather_table: str
    bq_location: str


def load_config(env: Optional[Mapping[str, str]] = None) -> Config:
    """Load configuration from environment variables.

    ``env`` defaults to ``os.environ`` but can be overridden (e.g. in
    tests) with any string-keyed mapping.
    """
    source = os.environ if env is None else env

    gcp_project_id = source.get("GCP_PROJECT_ID")
    if not gcp_project_id:
        raise ValueError(
            "GCP_PROJECT_ID is required and must be set in the environment "
            "(this is your own billing/query-execution project -- never "
            "hardcoded)."
        )

    # `or` (not a plain dict .get default) so that a present-but-empty
    # value -- e.g. a blank line sourced from config/.env.example --
    # falls back to the default just like a missing key would.
    citibike_table = source.get("BQ_CITIBIKE_TABLE") or DEFAULT_CITIBIKE_TABLE
    weather_table = source.get("BQ_WEATHER_TABLE") or DEFAULT_WEATHER_TABLE
    bq_location = source.get("BQ_LOCATION") or DEFAULT_BQ_LOCATION

    # Validate at load time so a malformed table ID fails fast, before any
    # client or query is ever built.
    validate_table_id(citibike_table)
    validate_table_id(weather_table)

    return Config(
        gcp_project_id=gcp_project_id,
        citibike_table=citibike_table,
        weather_table=weather_table,
        bq_location=bq_location,
    )
