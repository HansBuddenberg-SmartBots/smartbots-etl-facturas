from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Optional

from src.domain.entities import InvoiceRecord


@dataclass
class UpsertResult:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    all_records: list[InvoiceRecord] = field(default_factory=list)

    @property
    def total_processed(self) -> int:
        return self.inserted + self.updated + self.unchanged


@dataclass
class ExecutionReport:
    run_id: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    status: str = "PENDING"  # SUCCESS | PARTIAL | ERROR | NO_FILES

    # Files
    source_files: list[str] = field(default_factory=list)
    files_with_errors: list[str] = field(default_factory=list)
    backup_file_id: Optional[str] = None
    rollback_executed: bool = False

    # Counters
    total_files: int = 0
    source_row_count: int = 0
    valid_row_count: int = 0
    inserted_count: int = 0
    updated_count: int = 0
    unchanged_count: int = 0
    error_count: int = 0

    # Financial
    source_total_amount: Decimal = Decimal("0")
    output_total_amount: Decimal = Decimal("0")

    # Errors
    validation_errors: list[dict] = field(default_factory=list)

    @property
    def amount_variance(self) -> Decimal:
        return abs(self.source_total_amount - self.output_total_amount)

    @property
    def has_errors(self) -> bool:
        return self.status not in ("SUCCESS", "NO_FILES")

    def to_template_vars(self) -> dict:
        return {
            "run_id": self.run_id,
            "timestamp": self.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "archivos_procesados": self.total_files,
            "registros_insertados": self.inserted_count,
            "registros_actualizados": self.updated_count,
            "registros_sin_cambios": self.unchanged_count,
            "total_monto_origen": f"${self.source_total_amount:,.0f}",
            "total_monto_destino": f"${self.output_total_amount:,.0f}",
            "varianza": f"${self.amount_variance:,.0f}",
            "errores_validacion": self._build_error_rows_html(),
            "error_tipo": self.status,
            "error_detalle": "; ".join(e.get("error", "") for e in self.validation_errors[:5]),
            "rollback_ejecutado": "Sí" if self.rollback_executed else "No",
        }

    def _build_error_rows_html(self) -> str:
        if not self.validation_errors:
            return ""
        rows = []
        for err in self.validation_errors[:20]:
            rows.append(
                f"<tr><td>{err.get('file', 'N/A')}</td>"
                f"<td>{err.get('row_index', 'N/A')}</td>"
                f"<td>{err.get('error', 'N/A')}</td></tr>"
            )
        if len(self.validation_errors) > 20:
            rows.append(
                f"<tr><td colspan='3'>... y {len(self.validation_errors) - 20} más</td></tr>"
            )
        return "\n".join(rows)
