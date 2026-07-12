"""Stage 6 analytics package.

Builds ONE dashboard-ready, daily-grain analytics table
(``citibike_weather_analytics``) from the EXISTING Stage 4/5 monthly
destination tables (``citibike_weather_monthly_YYYY_MM``) -- never from
the raw public source files.

Modules:
  - ``analytics_query``   -- pure SQL builder + derived-field constants
                             and their Python classifiers (no I/O).
  - ``discovery``         -- find the monthly destination tables to
                             combine (pure selection logic + a thin
                             ``list_tables`` I/O wrapper).
  - ``analytics_validation`` -- pure post-load validation logic.
  - ``analytics_pipeline``   -- orchestration (injected clients/loader).

The idempotent ``CREATE OR REPLACE TABLE`` load itself lives in
``src.loading.analytics_loader`` (loaders live in ``src/loading/`` per
the README folder table); see ``DECISIONS.md`` D-027.
"""
