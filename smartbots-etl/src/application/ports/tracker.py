"""Port para tracking de ejecuciones."""

from __future__ import annotations

from typing import Any, Protocol


class Tracker(Protocol):
    def start_run(self, run_uuid: str) -> None:
        """Registra inicio de ejecución."""
        ...

    def finish_run(self, run_uuid: str, status: str, counters: dict[str, Any]) -> None:
        """Registra fin de ejecución con contadores finales."""
        ...

    def log_file_start(
        self,
        run_uuid: str,
        file_name: str,
        file_drive_id: str,
        file_modified_time: str | None = None,
    ) -> int:
        """Registra inicio de procesamiento de archivo. Retorna file_log_id."""
        ...

    def log_file_schema(
        self,
        file_log_id: int,
        valid: bool,
        missing: list[str],
        extra: list[str],
    ) -> None:
        """Registra resultado de validación de schema."""
        ...

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
        ...

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
        ...

    def log_records_batch(self, records: list[dict[str, Any]]) -> None:
        """Insert batch de registros para mejor performance."""
        ...

    def is_file_processed(self, file_name: str, modified_time: str) -> bool:
        """Verifica si un archivo ya fue procesado exitosamente (idempotencia)."""
        ...

    def get_run_summary(self, run_uuid: str) -> dict[str, Any]:
        """Retorna resumen de una ejecución."""
        ...
