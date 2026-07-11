import json

from src.pipeline.batch_log import JsonlBatchLogger, new_run_id


def test_new_run_id_is_unique_string():
    a = new_run_id()
    b = new_run_id()
    assert isinstance(a, str) and isinstance(b, str)
    assert a != b


def test_log_writes_one_json_line_per_record(tmp_path):
    path = tmp_path / "batch.jsonl"
    logger = JsonlBatchLogger(path=str(path), run_id="test-run")
    logger.log_month_run(year=2025, month=1, table_name="x", status="success", exit_code=0, reason=None)
    logger.log_month_run(
        year=2025, month=2, table_name="y", status="skipped", exit_code=None, reason="stopped_after_failure"
    )
    logger.log_summary(requested_months=2, succeeded=1, failed=0, skipped=1, exit_code=0, total_estimated_bytes=None)
    logger.close()

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3

    records = [json.loads(line) for line in lines]
    assert records[0]["record_type"] == "month_run"
    assert records[0]["table_name"] == "x"
    assert records[0]["status"] == "success"

    assert records[1]["record_type"] == "month_run"
    assert records[1]["status"] == "skipped"
    assert records[1]["reason"] == "stopped_after_failure"

    assert records[2]["record_type"] == "batch_summary"
    assert records[2]["succeeded"] == 1

    assert all(r["run_id"] == "test-run" for r in records)
    assert all("timestamp" in r for r in records)


def test_month_run_used_for_both_attempted_and_skipped_months(tmp_path):
    # Confirms there is no separate "skipped" record type -- every
    # requested month, attempted or not, is a "month_run" record.
    path = tmp_path / "batch.jsonl"
    logger = JsonlBatchLogger(path=str(path), run_id="test-run")
    logger.log_month_run(year=2025, month=1, table_name="a", status="success", exit_code=0, reason=None)
    logger.log_month_run(year=2025, month=2, table_name="b", status="failure", exit_code=6, reason=None)
    logger.log_month_run(year=2025, month=3, table_name="c", status="skipped", exit_code=None, reason="stopped_after_failure")
    logger.close()

    records = [json.loads(line) for line in path.read_text(encoding="utf-8").strip().splitlines()]
    assert {r["record_type"] for r in records} == {"month_run"}
    assert {r["status"] for r in records} == {"success", "failure", "skipped"}


def test_creates_parent_directory_if_missing(tmp_path):
    path = tmp_path / "nested" / "dir" / "batch.jsonl"
    logger = JsonlBatchLogger(path=str(path), run_id="test-run")
    logger.log_summary(requested_months=0, succeeded=0, failed=0, skipped=0, exit_code=0, total_estimated_bytes=None)
    logger.close()
    assert path.exists()


def test_records_append_across_logger_instances(tmp_path):
    path = tmp_path / "batch.jsonl"
    first = JsonlBatchLogger(path=str(path), run_id="run-1")
    first.log_summary(requested_months=1, succeeded=1, failed=0, skipped=0, exit_code=0, total_estimated_bytes=None)
    first.close()

    second = JsonlBatchLogger(path=str(path), run_id="run-2")
    second.log_summary(requested_months=1, succeeded=1, failed=0, skipped=0, exit_code=0, total_estimated_bytes=None)
    second.close()

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2


def test_write_failure_after_file_closed_raises(tmp_path):
    # Proves JsonlBatchLogger does NOT swallow write failures itself --
    # batch_pipeline._safe_log is what maps this to exit code 8.
    path = tmp_path / "batch.jsonl"
    logger = JsonlBatchLogger(path=str(path), run_id="test-run")
    logger.close()
    try:
        logger.log_summary(requested_months=0, succeeded=0, failed=0, skipped=0, exit_code=0, total_estimated_bytes=None)
    except ValueError:
        pass  # writing to a closed file object raises ValueError -- expected
    else:
        raise AssertionError("expected a write-after-close failure to raise")
