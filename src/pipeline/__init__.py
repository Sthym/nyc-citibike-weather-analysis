"""Stage 4: reusable monthly ETL pipeline.

Generalizes the Stage 3 one-month (January 2025) prototype so the same
query builder, loader, and validator can process any valid month without
changing Python or SQL source code. Month/date validation lives here as
pure logic (``month_period.py``); the live-BigQuery orchestration that
CLI scripts call into lives in ``monthly_pipeline.py``.
"""
