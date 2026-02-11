import tempfile
from pathlib import Path

import pytest

from src.infrastructure.sqlite_tracker import SqliteTracker


@pytest.fixture
def tracker(tmp_path):
    db_path = str(tmp_path / "test_tracking.db")
    t = SqliteTracker(db_path=db_path)
    yield t
    t.close()


class TestStartAndFinishRun:
    def test_start_run_creates_record(self, tracker):
        tracker.start_run("run-001")
        summary = tracker.get_run_summary("run-001")
        assert summary["run_uuid"] == "run-001"
        assert summary["status"] == "RUNNING"

    def test_finish_run_updates_record(self, tracker):
        tracker.start_run("run-002")
        tracker.finish_run(
            "run-002",
            "SUCCESS",
            {
                "total_files": 3,
                "total_records": 100,
                "inserted": 80,
                "updated": 15,
                "unchanged": 5,
                "errors": 0,
            },
        )
        summary = tracker.get_run_summary("run-002")
        assert summary["status"] == "SUCCESS"
        assert summary["total_files"] == 3
        assert summary["inserted"] == 80
        assert summary["finished_at"] is not None

    def test_get_run_summary_nonexistent_returns_empty(self, tracker):
        assert tracker.get_run_summary("nope") == {}


class TestFileLog:
    def test_log_file_start_returns_id(self, tracker):
        tracker.start_run("run-003")
        file_id = tracker.log_file_start(
            "run-003", "test.xlsx", "drive-id-1", "2026-01-15T10:00:00Z"
        )
        assert isinstance(file_id, int)
        assert file_id > 0

    def test_log_file_schema(self, tracker):
        tracker.start_run("run-004")
        fid = tracker.log_file_start("run-004", "test.xlsx", "d-1")
        tracker.log_file_schema(fid, True, [], [])
        tracker.log_file_schema(fid, False, ["Col A"], ["Col X"])

    def test_log_file_finish(self, tracker):
        tracker.start_run("run-005")
        fid = tracker.log_file_start("run-005", "test.xlsx", "d-1")
        tracker.log_file_finish(
            fid, "COMPLETED", rows_total=50, rows_valid=48, rows_error=2, error_message=None
        )

    def test_log_file_finish_with_error(self, tracker):
        tracker.start_run("run-006")
        fid = tracker.log_file_start("run-006", "bad.xlsx", "d-2")
        tracker.log_file_finish(fid, "ERROR", 0, 0, 0, "Schema invalido")


class TestRecordLog:
    def test_log_single_record(self, tracker):
        tracker.start_run("run-010")
        fid = tracker.log_file_start("run-010", "t.xlsx", "d-1")
        tracker.log_record("run-010", fid, 0, "F-001", "R-001", "INSERT", None)

    def test_log_records_batch(self, tracker):
        tracker.start_run("run-011")
        fid = tracker.log_file_start("run-011", "t.xlsx", "d-1")
        batch = [
            {
                "run_uuid": "run-011",
                "file_log_id": fid,
                "row_index": 0,
                "invoice_number": "F-1",
                "reference_number": "R-1",
                "action": "INSERT",
                "error_message": None,
            },
            {
                "run_uuid": "run-011",
                "file_log_id": fid,
                "row_index": 1,
                "invoice_number": "F-2",
                "reference_number": "R-2",
                "action": "UPDATE",
                "error_message": None,
            },
            {
                "run_uuid": "run-011",
                "file_log_id": fid,
                "row_index": 2,
                "invoice_number": None,
                "reference_number": None,
                "action": "VALIDATION_ERROR",
                "error_message": "Campo vacio",
            },
        ]
        tracker.log_records_batch(batch)


class TestIdempotency:
    def test_is_file_processed_false_initially(self, tracker):
        assert tracker.is_file_processed("new.xlsx", "2026-01-15T10:00:00Z") is False

    def test_is_file_processed_true_after_completion(self, tracker):
        tracker.start_run("run-020")
        fid = tracker.log_file_start("run-020", "done.xlsx", "d-1", "2026-01-15T10:00:00Z")
        tracker.log_file_finish(fid, "COMPLETED", 10, 10, 0, None)
        assert tracker.is_file_processed("done.xlsx", "2026-01-15T10:00:00Z") is True

    def test_is_file_processed_false_if_errored(self, tracker):
        tracker.start_run("run-021")
        fid = tracker.log_file_start("run-021", "fail.xlsx", "d-2", "2026-01-15T10:00:00Z")
        tracker.log_file_finish(fid, "ERROR", 0, 0, 0, "boom")
        assert tracker.is_file_processed("fail.xlsx", "2026-01-15T10:00:00Z") is False

    def test_is_file_processed_false_different_modified_time(self, tracker):
        tracker.start_run("run-022")
        fid = tracker.log_file_start("run-022", "test.xlsx", "d-1", "2026-01-15T10:00:00Z")
        tracker.log_file_finish(fid, "COMPLETED", 10, 10, 0, None)
        assert tracker.is_file_processed("test.xlsx", "2026-01-16T10:00:00Z") is False
