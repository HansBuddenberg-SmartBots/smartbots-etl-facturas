"""Entidades de dominio del proceso de consolidación de facturas."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional


class RecordStatus(Enum):
    """Estado de un registro durante el procesamiento."""

    NEW = "new"  # No existe en consolidado → se agregará
    UPDATED = "updated"  # Existe en consolidado → se actualizará
    UNCHANGED = "unchanged"  # Existe y no tiene cambios
    ERROR = "error"  # Falló validación


@dataclass(frozen=True, kw_only=True)
class InvoiceRecord:
    """
    Entidad central: una fila de factura de transporte.

    Representa tanto filas del archivo origen como del consolidado.
    Inmutable — las transformaciones crean nuevas instancias.
    """

    # === Clave primaria compuesta ===
    invoice_number: str
    reference_number: str  # N° Guía / BL / Booking

    # === Campos de negocio ===
    carrier_name: str
    ship_name: str
    dispatch_guides: str
    invoice_date: date
    description: str
    net_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    currency: str = "CLP"

    # === Campos adicionales del consolidado ===
    fecha_recepcion_digital: str = ""
    aprobado_por: str = ""
    estado_operaciones: str = ""
    fecha_aprobacion_operaciones: str = ""

    # === Metadatos de procesamiento (no son clave primaria) ===
    source_file: Optional[str] = None
    processed_at: Optional[datetime] = None
    status: RecordStatus = RecordStatus.NEW

    def __post_init__(self) -> None:
        """Validaciones de invariantes de dominio."""
        if not self.invoice_number or not self.invoice_number.strip():
            raise ValueError("invoice_number no puede estar vacío")
        if not self.reference_number or not self.reference_number.strip():
            raise ValueError("reference_number no puede estar vacío")
        if not self.carrier_name or not self.carrier_name.strip():
            raise ValueError("carrier_name no puede estar vacío")
        # ship_name y dispatch_guides son opcionales (pueden estar vacíos)
        if self.total_amount < 0:
            raise ValueError(f"total_amount no puede ser negativo: {self.total_amount}")
        # Validación cruzada: total ≈ net + tax
        expected = self.net_amount + self.tax_amount
        if abs(self.total_amount - expected) > Decimal("1"):
            raise ValueError(
                f"total_amount ({self.total_amount}) no coincide con "
                f"net ({self.net_amount}) + tax ({self.tax_amount}) = {expected}"
            )

    @property
    def primary_key(self) -> tuple[str, str]:
        """Clave compuesta para matching en upsert."""
        return (self.invoice_number.strip(), self.reference_number.strip())

    def with_status(self, new_status: RecordStatus) -> "InvoiceRecord":
        """Retorna copia con status actualizado."""
        return InvoiceRecord(
            invoice_number=self.invoice_number,
            reference_number=self.reference_number,
            carrier_name=self.carrier_name,
            ship_name=self.ship_name,
            dispatch_guides=self.dispatch_guides,
            invoice_date=self.invoice_date,
            description=self.description,
            net_amount=self.net_amount,
            tax_amount=self.tax_amount,
            total_amount=self.total_amount,
            currency=self.currency,
            fecha_recepcion_digital=self.fecha_recepcion_digital,
            aprobado_por=self.aprobado_por,
            estado_operaciones=self.estado_operaciones,
            fecha_aprobacion_operaciones=self.fecha_aprobacion_operaciones,
            source_file=self.source_file,
            processed_at=self.processed_at,
            status=new_status,
        )

    def has_changes_vs(self, other: "InvoiceRecord") -> bool:
        """Compara campos de negocio (ignora metadatos)."""
        return (
            self.carrier_name != other.carrier_name
            or self.ship_name != other.ship_name
            or self.dispatch_guides != other.dispatch_guides
            or self.invoice_date != other.invoice_date
            or self.net_amount != other.net_amount
            or self.tax_amount != other.tax_amount
            or self.total_amount != other.total_amount
        )
