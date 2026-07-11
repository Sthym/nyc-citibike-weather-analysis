"""JSONL run logging for the Stage 5 batch pipeline.

Runtime logs are gitignored (see ``.gitignore``'s ``logs/`` pattern) --
never committed. Each batch run writes ONE JSONL file with exactly two
record types:

  - ``"month_run"`` -- one record per requested month, whether it was
    actually attempted (``status`` "success"/"failure", carrying that
    month's own Stage 4 exit code) or never attempted (``status``
    "skipped", carrying a ``reason``: "preflight_failed" or
    "stopped_after_failure"). Every requested month gets exactly one of
    these -- skipped months are NOT a separate record type.
  - ``"batch_summary"`` -- exactly one final record per run, aggregating
    counts, the overall exit code, and (dry-run only) the batch's total
    estimated bytes processed.

``JsonlBatchLogger`` is injected into ``batch_pipeline.execute_batch``
the same way ``read_client``/``query_client``/``loader`` are injected
into ``monthly_pipeline.execute`` -- tests substitute an in-memory fake
implementing the same ``log_month_run``/``log_summary`` interface, so no
test needs to touch the filesystem to exercise batch control flow. If a
write to the underlying file fails (disk full, permission revoked,
directory removed mid-run, etc.), the exception propagates to the
caller, which is responsible for mapping that into exit code 8 (logging
failure) -- see ``batch_pipeline._safe_log``.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict


def new_run_id() -> str:
    """A sortable, collision-resistant identifier for one batch run."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{uuid.uuid4().hex[:8]}"


class JsonlBatchLogger:
    """Appends one JSON object per line to a run-specific log file.

    Every record automatically gets ``record_type``, ``run_id``, and a
    UTC ``timestamp``. The file is flushed after every write so a batch
    that crashes or is killed mid-run still leaves a readable partial
    log behind. Write failures are NOT swallowed here -- they propagate
    so the caller can react (see module docstring).
    """

    def __init__(self, path: str, run_id: str):
        self.path = path
        self.run_id = run_id
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._fh = open(path, "a", encoding="utf-8")

    def _write(self, record_type: str, fields: Dict[str, Any]) -> None:
        record = {
            "record_type": record_type,
            "run_id": self.run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **fields,
        }
        self._fh.write(json.dumps(record, default=str) + "\n")
        self._fh.flush()

    def log_month_run(self, **fields: Any) -> None:
        """One record per requested month -- attempted (success/failure)
        or skipped. See class docstring for the field conventions.
        """
        self._write("month_run", fields)

    def log_summary(self, **fields: Any) -> None:
        """Exactly one final record per batch run."""
        self._write("batch_summary", fields)

    def close(self) -> None:
        self._fh.close()
