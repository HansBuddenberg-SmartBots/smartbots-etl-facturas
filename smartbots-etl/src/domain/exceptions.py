"""Excepciones de negocio del proceso de consolidación."""

from decimal import Decimal


class ConsolidationError(Exception):
    """Base para errores del proceso de consolidación."""


class SourceFileNotFoundError(ConsolidationError):
    """No se encontraron archivos en la carpeta origen."""


class SchemaValidationError(ConsolidationError):
    """El archivo origen no tiene la estructura esperada."""

    def __init__(self, missing_columns: list[str], extra_columns: list[str]) -> None:
        self.missing_columns = missing_columns
        self.extra_columns = extra_columns
        super().__init__(
            f"Columnas faltantes: {missing_columns}, inesperadas: {extra_columns}"
        )


class RowValidationError(ConsolidationError):
    """Una o más filas no pasaron validación."""

    def __init__(self, errors: list[dict]) -> None:
        self.errors = errors
        super().__init__(f"{len(errors)} filas con errores de validación")


class ReconciliationError(ConsolidationError):
    """La reconciliación post-upsert detectó discrepancias críticas."""

    def __init__(self, data_loss_pct: float, amount_variance: Decimal) -> None:
        self.data_loss_pct = data_loss_pct
        self.amount_variance = amount_variance
        super().__init__(
            f"Reconciliación fallida: data_loss={data_loss_pct:.2f}%, "
            f"amount_variance={amount_variance}"
        )


class RollbackExecutedError(ConsolidationError):
    """Se ejecutó rollback tras fallo en actualización."""

    def __init__(self, reason: str, backup_path: str) -> None:
        self.reason = reason
        self.backup_path = backup_path
        super().__init__(f"Rollback ejecutado: {reason}. Backup: {backup_path}")


class IdempotencySkipError(ConsolidationError):
    """Archivo ya procesado (check de idempotencia)."""
