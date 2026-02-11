"""Tracker de ejecuciones basado en SQLite con logging a nivel de archivo y registro."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS execution_runs (
    run_uuid            TEXT PRIMARY KEY,
    started_at          TEXT NOT NULL,
    finished_at         TEXT,
    status              TEXT NOT NULL,
    total_files         INTEGER DEFAULT 0,
    total_records       INTEGER DEFAULT 0,
    inserted            INTEGER DEFAULT 0,
    updated             INTEGER DEFAULT 0,
    unchanged           INTEGER DEFAULT 0,
    errors              INTEGER DEFAULT 0,
    source_total_amount TEXT,
    output_total_amount TEXT,
    message             TEXT
);

CREATE TABLE IF NOT EXISTS file_log (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    run_uuid            TEXT NOT NULL REFERENCES execution_runs(run_uuid),
    file_name           TEXT NOT NULL,
    file_drive_id       TEXT,
    file_modified_time  TEXT,
    schema_valid        INTEGER,
    missing_columns     TEXT,
    extra_columns       TEXT,
    rows_total          INTEGER DEFAULT 0,
    rows_valid          INTEGER DEFAULT 0,
    rows_error          INTEGER DEFAULT 0,
    status              TEXT NOT NULL,
    error_message       TEXT,
    started_at          TEXT NOT NULL,
    finished_at         TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS record_log (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    run_uuid            TEXT NOT NULL REFERENCES execution_runs(run_uuid),
    file_log_id         INTEGER NOT NULL REFERENCES file_log(id),
    row_index           INTEGER NOT NULL,
    invoice_number      TEXT,
    reference_number    TEXT,
    action              TEXT NOT NULL,
    error_message       TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_file_log_run ON file_log(run_uuid);
CREATE INDEX IF NOT EXISTS idx_record_log_run ON record_log(run_uuid);
CREATE INDEX IF NOT EXISTS idx_record_log_file ON record_log(file_log_id);
CREATE INDEX IF NOT EXISTS idx_record_log_action ON record_log(action);
"""


class SqliteTracker:
    """Rastrea ejecuciones ETL con granularidad a nivel de archivo y registro."""

    def __init__(self, db_path: str) -> None:
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        logger.info("sqlite_tracker_initialized", db_path=db_path)

    def start_run(self, run_uuid: str) -> None:
        """Registra inicio de ejecución."""
        now = datetime.now(UTC).isoformat()
        self._conn.execute(
            "INSERT INTO execution_runs (run_uuid, started_at, status) VALUES (?, ?, ?)",
            (run_uuid, now, "RUNNING"),
        )
        self._conn.commit()
        logger.info("tracker_run_started", run_uuid=run_uuid)

    def finish_run(self, run_uuid: str, status: str, counters: dict[str, Any]) -> None:
        """Registra fin de ejecución con contadores finales."""
        now = datetime.now(UTC).isoformat()
        self._conn.execute(
            """UPDATE execution_runs
               SET finished_at=?, status=?,
                   total_files=?, total_records=?,
                   inserted=?, updated=?, unchanged=?, errors=?,
                   source_total_amount=?, output_total_amount=?,
                   message=?
               WHERE run_uuid=?""",
            (
                now,
                status,
                counters.get("total_files", 0),
                counters.get("total_records", 0),
                counters.get("inserted", 0),
                counters.get("updated", 0),
                counters.get("unchanged", 0),
                counters.get("errors", 0),
                counters.get("source_total_amount", "0"),
                counters.get("output_total_amount", "0"),
                counters.get("message", ""),
                run_uuid,
            ),
        )
        self._conn.commit()
        logger.info("tracker_run_finished", run_uuid=run_uuid, status=status)

    def log_file_start(
        self,
        run_uuid: str,
        file_name: str,
        file_drive_id: str,
        file_modified_time: str | None = None,
    ) -> int:
        """Registra inicio de procesamiento de archivo. Retorna file_log_id."""
        now = datetime.now(UTC).isoformat()
        cursor = self._conn.execute(
            """INSERT INTO file_log
               (run_uuid, file_name, file_drive_id, file_modified_time, status, started_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (run_uuid, file_name, file_drive_id, file_modified_time, "PROCESSING", now),
        )
        self._conn.commit()
        file_log_id = cursor.lastrowid
        assert file_log_id is not None
        logger.info("tracker_file_started", file_name=file_name, file_log_id=file_log_id)
        return file_log_id

    def log_file_schema(
        self,
        file_log_id: int,
        valid: bool,
        missing: list[str],
        extra: list[str],
    ) -> None:
        """Registra resultado de validación de schema para un archivo."""
        self._conn.execute(
            """UPDATE file_log
               SET schema_valid=?, missing_columns=?, extra_columns=?
               WHERE id=?""",
            (
                1 if valid else 0,
                json.dumps(missing, ensure_ascii=False),
                json.dumps(extra, ensure_ascii=False),
                file_log_id,
            ),
        )
        self._conn.commit()

    def log_file_finish(
        self,
        file_log_id: int,
        status: str,
        rows_total: int,
        rows_valid: int,
        rows_error: int,
        error_message: str | None,
    ) -> None:
        """Registra finalización de procesamiento de archivo."""
        now = datetime.now(UTC).isoformat()
        self._conn.execute(
            """UPDATE file_log
               SET status=?, finished_at=?,
                   rows_total=?, rows_valid=?, rows_error=?,
                   error_message=?
               WHERE id=?""",
            (status, now, rows_total, rows_valid, rows_error, error_message, file_log_id),
        )
        self._conn.commit()
        logger.info(
            "tracker_file_finished",
            file_log_id=file_log_id,
            status=status,
            rows_total=rows_total,
        )

    def log_record(
        self,
        run_uuid: str,
        file_log_id: int,
        row_index: int,
        invoice_number: str | None,
        reference_number: str | None,
        action: str,
        error_message: str | None,
    ) -> None:
        """Registra resultado de procesamiento de registro individual."""
        self._conn.execute(
            """INSERT INTO record_log
               (run_uuid, file_log_id, row_index, invoice_number,
                reference_number, action, error_message)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                run_uuid,
                file_log_id,
                row_index,
                invoice_number,
                reference_number,
                action,
                error_message,
            ),
        )
        self._conn.commit()

    def log_records_batch(self, records: list[dict[str, Any]]) -> None:
        """Insert batch de registros para mejor performance."""
        self._conn.executemany(
            """INSERT INTO record_log
               (run_uuid, file_log_id, row_index, invoice_number,
                reference_number, action, error_message)
               VALUES (:run_uuid, :file_log_id, :row_index, :invoice_number,
                       :reference_number, :action, :error_message)""",
            records,
        )
        self._conn.commit()
        logger.info("tracker_records_batch", count=len(records))

    def is_file_processed(self, file_name: str, modified_time: str) -> bool:
        """Verifica si un archivo ya fue procesado exitosamente (idempotencia)."""
        cursor = self._conn.execute(
            """SELECT 1 FROM file_log
               WHERE file_name=? AND file_modified_time=? AND status='COMPLETED'
               LIMIT 1""",
            (file_name, modified_time),
        )
        return cursor.fetchone() is not None

    def get_run_summary(self, run_uuid: str) -> dict[str, Any]:
        """Retorna resumen de una ejecución."""
        cursor = self._conn.execute(
            "SELECT * FROM execution_runs WHERE run_uuid=?",
            (run_uuid,),
        )
        row = cursor.fetchone()
        if not row:
            return {}
        columns = [desc[0] for desc in cursor.description]
        return dict(zip(columns, row))

    def close(self) -> None:
        """Cierra la conexión a la base de datos."""
        self._conn.close()
