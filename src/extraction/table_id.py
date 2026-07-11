"""Validation for fully-qualified BigQuery table IDs.

Enforces a strict character allow-list before any table identifier is
ever interpolated into SQL, then delegates final structural validation
to BigQuery's own parser (`google.cloud.bigquery.TableReference.from_string`).
This is defense in depth: the allow-list blocks obviously unsafe input
fast and cheaply; the SDK parser has the final say on well-formedness.
"""
from __future__ import annotations

import re

from google.cloud import bigquery

# Reject backticks, quotes, whitespace, and semicolons outright -- these
# have no legitimate place in a BigQuery project/dataset/table identifier
# and are exactly the characters an injection attempt would need.
_UNSAFE_CHARS = re.compile(r"[`'\";\s]")

# BigQuery project IDs may contain hyphens (e.g. "nyu-datasets").
_PROJECT_RE = re.compile(r"^[A-Za-z0-9-]{1,63}$")

# BigQuery dataset IDs may NOT contain hyphens -- letters, digits, and
# underscores only.
_DATASET_RE = re.compile(r"^[A-Za-z0-9_]{1,1024}$")

# Table IDs follow the same rule as dataset IDs.
_TABLE_RE = re.compile(r"^[A-Za-z0-9_]{1,1024}$")


def validate_table_id(table_id: str) -> bigquery.TableReference:
    """Validate a fully-qualified ``project.dataset.table`` string.

    Raises ``ValueError`` for anything that isn't a safe, well-formed
    BigQuery table reference. Returns a ``bigquery.TableReference`` on
    success, so callers get a validated, structured object rather than a
    raw string they'd need to re-parse or re-trust.
    """
    if not isinstance(table_id, str) or not table_id:
        raise ValueError(f"table_id must be a non-empty string: {table_id!r}")

    if _UNSAFE_CHARS.search(table_id):
        raise ValueError(f"table_id contains disallowed characters: {table_id!r}")

    parts = table_id.split(".")
    if len(parts) != 3:
        raise ValueError(
            f"table_id must be in the form project.dataset.table: {table_id!r}"
        )

    project, dataset, table = parts

    if not _PROJECT_RE.match(project):
        raise ValueError(f"invalid project segment: {project!r}")
    if not _DATASET_RE.match(dataset):
        raise ValueError(f"invalid dataset segment (hyphens not allowed): {dataset!r}")
    if not _TABLE_RE.match(table):
        raise ValueError(f"invalid table segment: {table!r}")

    # Defense in depth: let BigQuery's own parser have the final say.
    return bigquery.TableReference.from_string(table_id)
