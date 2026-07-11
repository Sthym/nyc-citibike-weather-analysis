"""Stage 5 orchestration: multi-month batch processing on top of the
Stage 4 reusable monthly pipeline.

This module adds NO new query, load, or validation logic of its own.
Every month in the requested range is executed by calling
``monthly_pipeline.execute`` (the exact Stage 4 function, unchanged) --
the same query builder, loader, and V1-V11 validator Stage 4 already
uses. ``execute_batch`` only adds: range enumeration, a strict
whole-range preflight check, stop-on-first-failure (default) /
``--continue-on-error`` control flow, and JSONL run logging.

``execute_month`` is accepted as an injectable parameter (defaulting to
the real ``monthly_pipeline.execute``) purely as a test seam -- exactly
the same DI pattern ``monthly_pipeline.execute`` itself uses for
``read_client``/``query_client``/``loader``. In production the default
is always used; batch-level unit tests substitute a fake so they can
exercise ordering/logging/exit-code control flow without re-simulating
BigQuery dispatch (that's already covered by ``test_monthly_pipeline.py``).

Exit codes
----------
Stage 5 reuses Stage 4's exit-code table EXACTLY for 0-7 (imported,
never redefined) and adds exactly one new, batch-specific code:

  0  success -- every requested month succeeded.
  1  unexpected internal error.
  2  CLI usage error.
  3  configuration error.
  4  invalid or unavailable month/range -- Stage 4's existing code,
     reused here for a whole-range preflight rejection: the ENTIRE
     requested range must be covered by the live shared source range,
     or NO month is processed and the batch returns 4.
  5  authentication/query error.
  6  load error.
  7  validation failure.
  8  logging failure -- the JSONL run log itself could not be written.
     This is the ONE new Stage 5 code and takes priority over any other
     outcome the moment it occurs, because a run log that can't be
     trusted going forward shouldn't report a misleadingly clean 0/4/5/
     6/7 either.

(5, 6, and 7 are also returned when DELEGATED from a single month's own
``monthly_pipeline.execute`` result -- see ``continue_on_error`` below.)
"""
from __future__ import annotations

import re
from typing import Callable, Dict, Optional

from src.pipeline.batch_period import (
    BatchPreflightError,
    months_in_range,
    preflight_validate_range,
)
from src.pipeline.month_period import compute_effective_range, monthly_table_name
from src.pipeline.monthly_pipeline import (
    EXIT_AUTH_OR_QUERY_ERROR,
    EXIT_INVALID_MONTH,
    EXIT_SUCCESS,
)
from src.pipeline.monthly_pipeline import execute as _execute_month_default

# EXIT_INVALID_RANGE is the SAME numeric value as Stage 4's
# EXIT_INVALID_MONTH (4) -- not a new code. The alias exists only so
# batch-level call sites read clearly ("range" vs a single "month").
EXIT_INVALID_RANGE = EXIT_INVALID_MONTH
EXIT_LOGGING_FAILURE = 8

_BYTES_ESTIMATE_RE = re.compile(r"estimated bytes processed:\s*(\d+)")


def _mode_label(dry_run: bool, validate_only: bool) -> str:
    if dry_run:
        return "dry-run"
    if validate_only:
        return "validate-only"
    return "normal"


def _capturing_print_fn(base_print_fn: Callable[[str], None], sink: Dict[str, int]) -> Callable[[str], None]:
    """Wrap a ``print_fn`` so the batch can observe the per-month bytes
    estimate Stage 4 already prints in ``--dry-run`` mode, WITHOUT
    recomputing it -- ``monthly_pipeline.execute`` prints
    ``"[DRY RUN] estimated bytes processed: <n>"``; this only parses
    that number out of the stream it already produces. No dry-run query
    logic is duplicated.
    """

    def _fn(line: str = "") -> None:
        base_print_fn(line)
        match = _BYTES_ESTIMATE_RE.search(str(line))
        if match:
            sink["bytes"] = int(match.group(1))

    return _fn


def _safe_log(action: Callable[[], None], print_fn: Callable[[str], None]) -> bool:
    """Run one logger call; return False (after printing a diagnostic)
    instead of letting a broken run log crash the batch with an
    uncaught exception. Callers map a False return to exit code 8.
    """
    try:
        action()
        return True
    except Exception as exc:  # noqa: BLE001 -- any log I/O failure is exit 8
        print_fn(f"[LOGGING ERROR] failed to write run log: {exc}")
        return False


def execute_batch(
    *,
    start_year: int,
    start_month: int,
    end_year: int,
    end_month: int,
    dry_run: bool,
    validate_only: bool,
    continue_on_error: bool,
    config,
    destination_project: str,
    destination_dataset: str,
    read_client,
    query_client,
    loader,
    logger,
    print_fn: Callable[[str], None] = print,
    execute_month: Callable[..., int] = _execute_month_default,
) -> int:
    """Run ``monthly_pipeline.execute`` once per month in
    [start_year/start_month .. end_year/end_month], inclusive, and
    return a single batch-level exit code. See the module docstring for
    the full exit-code table.

    Order of operations:
      1. Enumerate the requested (year, month) range (assumes the
         caller -- the CLI script -- already validated shape/order via
         ``month_period.parse_year_month`` + ``batch_period.months_in_range``).
      2. Fetch LIVE source date ranges once for the whole batch -> 5 on
         failure (same failure mode Stage 4 uses for the same live call).
      3. STRICT whole-range preflight: every requested month must be
         fully covered by the live effective shared range, or the ENTIRE
         batch is rejected before any month runs -> 4. All invalid
         months are reported, not just the first; every requested month
         is logged as a skipped "month_run" record (reason:
         preflight_failed).
      4. Process months in order, delegating each one to
         ``execute_month`` (Stage 4's ``execute``) unchanged:
           - normal / dry-run / validate-only mode is simply forwarded.
           - default (``continue_on_error=False``): stop at the first
             non-zero exit code; every remaining month is logged as a
             skipped "month_run" record (reason: stopped_after_failure),
             never attempted.
           - ``continue_on_error=True``: every month is attempted
             regardless of earlier failures.
      5. The overall exit code is 0 if every month succeeded, otherwise
         the exit code of the FIRST month that failed, in chronological
         order -- never a new code invented for "some months failed".
      6. Exactly one final "batch_summary" record is written, including
         ``total_estimated_bytes`` (the sum of every attempted month's
         captured dry-run bytes estimate when ``dry_run`` is True;
         ``None``/null in normal and validate-only mode).

    If writing ANY log record fails, ``execute_batch`` stops immediately
    and returns 8, regardless of what the batch's outcome would
    otherwise have been.
    """
    months = months_in_range(start_year, start_month, end_year, end_month)

    try:
        citibike_stats = read_client.get_date_range_stats(config.citibike_table)
        weather_stats = read_client.get_date_range_stats(config.weather_table)
    except Exception as exc:  # noqa: BLE001 -- any live-call failure is exit 5
        print_fn(f"[AUTH/QUERY ERROR] failed to retrieve live source date ranges: {exc}")
        logged = _safe_log(
            lambda: logger.log_summary(
                requested_months=len(months),
                succeeded=0,
                failed=0,
                skipped=len(months),
                exit_code=EXIT_AUTH_OR_QUERY_ERROR,
                mode=_mode_label(dry_run, validate_only),
                continue_on_error=continue_on_error,
                outcome="source_range_error",
                total_estimated_bytes=(0 if dry_run else None),
            ),
            print_fn,
        )
        return EXIT_LOGGING_FAILURE if not logged else EXIT_AUTH_OR_QUERY_ERROR

    effective_min_date, effective_max_date = compute_effective_range(
        citibike_stats["min_date"],
        citibike_stats["max_date"],
        weather_stats["min_date"],
        weather_stats["max_date"],
    )

    try:
        periods = preflight_validate_range(months, effective_min_date, effective_max_date)
    except BatchPreflightError as exc:
        print_fn(f"[BATCH PREFLIGHT FAILURE] {exc}")
        for year, month in months:
            logged = _safe_log(
                lambda year=year, month=month: logger.log_month_run(
                    year=year,
                    month=month,
                    table_name=monthly_table_name(year, month),
                    status="skipped",
                    exit_code=None,
                    reason="preflight_failed",
                ),
                print_fn,
            )
            if not logged:
                return EXIT_LOGGING_FAILURE
        logged = _safe_log(
            lambda: logger.log_summary(
                requested_months=len(months),
                succeeded=0,
                failed=0,
                skipped=len(months),
                exit_code=EXIT_INVALID_RANGE,
                mode=_mode_label(dry_run, validate_only),
                continue_on_error=continue_on_error,
                outcome="preflight_failed",
                total_estimated_bytes=(0 if dry_run else None),
            ),
            print_fn,
        )
        return EXIT_LOGGING_FAILURE if not logged else EXIT_INVALID_RANGE

    print_fn(
        f"[BATCH] preflight passed for {len(periods)} month(s): "
        f"{periods[0].start_date} .. {periods[-1].end_date}"
    )

    succeeded = 0
    failed = 0
    first_failure_exit_code: Optional[int] = None
    stopped_early = False
    total_estimated_bytes: Optional[int] = 0 if dry_run else None

    for idx, period in enumerate(periods):
        table_name = monthly_table_name(period.year, period.month)
        print_fn(
            f"[BATCH] ({idx + 1}/{len(periods)}) {period.year:04d}-{period.month:02d} -> {table_name}"
        )
        capture: Dict[str, int] = {}
        result = execute_month(
            year=period.year,
            month=period.month,
            table_name=table_name,
            dry_run=dry_run,
            validate_only=validate_only,
            config=config,
            destination_project=destination_project,
            destination_dataset=destination_dataset,
            read_client=read_client,
            query_client=query_client,
            loader=loader,
            print_fn=_capturing_print_fn(print_fn, capture),
        )
        if dry_run and "bytes" in capture:
            total_estimated_bytes = (total_estimated_bytes or 0) + capture["bytes"]

        status = "success" if result == EXIT_SUCCESS else "failure"
        logged = _safe_log(
            lambda period=period, table_name=table_name, result=result, status=status: logger.log_month_run(
                year=period.year,
                month=period.month,
                table_name=table_name,
                status=status,
                exit_code=result,
                reason=None,
            ),
            print_fn,
        )
        if not logged:
            return EXIT_LOGGING_FAILURE

        if result == EXIT_SUCCESS:
            succeeded += 1
            continue

        failed += 1
        if first_failure_exit_code is None:
            first_failure_exit_code = result

        if not continue_on_error:
            stopped_early = True
            for remaining_period in periods[idx + 1 :]:
                remaining_table = monthly_table_name(remaining_period.year, remaining_period.month)
                logged = _safe_log(
                    lambda remaining_period=remaining_period, remaining_table=remaining_table: logger.log_month_run(
                        year=remaining_period.year,
                        month=remaining_period.month,
                        table_name=remaining_table,
                        status="skipped",
                        exit_code=None,
                        reason="stopped_after_failure",
                    ),
                    print_fn,
                )
                if not logged:
                    return EXIT_LOGGING_FAILURE
            break

    skipped = len(periods) - succeeded - failed
    overall_exit_code = EXIT_SUCCESS if first_failure_exit_code is None else first_failure_exit_code

    print_fn(
        f"[BATCH SUMMARY] requested={len(periods)} succeeded={succeeded} "
        f"failed={failed} skipped={skipped} continue_on_error={continue_on_error} "
        f"stopped_early={stopped_early} exit_code={overall_exit_code}"
    )
    logged = _safe_log(
        lambda: logger.log_summary(
            requested_months=len(periods),
            succeeded=succeeded,
            failed=failed,
            skipped=skipped,
            exit_code=overall_exit_code,
            mode=_mode_label(dry_run, validate_only),
            continue_on_error=continue_on_error,
            stopped_early=stopped_early,
            outcome="completed",
            total_estimated_bytes=total_estimated_bytes,
        ),
        print_fn,
    )
    return EXIT_LOGGING_FAILURE if not logged else overall_exit_code
