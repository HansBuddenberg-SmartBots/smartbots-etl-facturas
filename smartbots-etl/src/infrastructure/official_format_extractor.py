"""Extractor oficial usando Pandas + Pydantic + Calamine (Rust backend)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
import structlog
from pydantic import BaseModel, Field, ValidationError

from src.application.config import ExcelConfig
from src.domain.entities import InvoiceRecord
from src.domain.exceptions import SchemaValidationError

logger = structlog.get_logger()


class FixedCells(BaseModel):
    """Celdas fijas del archivo origen."""

    empresa_transporte: str | None = Field(None, alias="B6")
    fecha_emision: str | None = Field(None, alias="B7")
    numero_factura: str | None = Field(None, alias="B8")
    nave: str | None = Field(None, alias="H6")
    puerto_embarque: str | None = Field(None, alias="H7")
    responsable: str | None = Field(None, alias="F4")

    @property
    def aprobado_por(self) -> str | None:
        """Limpia el prefijo 'Aprobado por: ' del responsable."""
        if self.responsable and isinstance(self.responsable, str):
            return self.responsable.replace("Aprobado por: ", "").strip()
        return self.responsable


class TabularRow(BaseModel):
    """Fila de datos tabulares desde fila 11."""

    fecha_servicio: str | None = Field(None, alias="Fecha Servicio")
    unidad: str | None = Field(None, alias="Unidad")
    conductor: str | None = Field(None, alias="Conductor")
    contenedor: str | None = Field(None, alias="Contenedor")
    patente_camion: str | None = Field(None, alias="Patente Camión")
    patente_carro: str | None = Field(None, alias="Patente Carro")
    ordenes_embarque: str | None = Field(None, alias="Órdenes de Embarque")
    plantas: str | None = Field(None, alias="Plantas")
    guias_despacho: str | None = Field(None, alias="Guías de Despacho")
    cantidad_pallets: Any | None = Field(None, alias="Cantidad Pallets")
    flete: Decimal | None = Field(None, alias="Flete($)")
    underslung: Decimal | None = Field(None, alias="Underslung($)")
    planta_adicional: Decimal | None = Field(None, alias="Planta Adicional ($)")
    retiro_cruzado: Decimal | None = Field(None, alias="Retiro Cruzado ($)")
    porteo: Decimal | None = Field(None, alias="Porteo($)")
    hora_llegada_planta: Any | None = Field(None, alias="Hora Llegada Planta")
    hora_salida_planta: Any | None = Field(None, alias="Hora Salida Planta")
    horas_sobre_estadia_planta: Any | None = Field(None, alias="Horas Sobre Estadía Planta")
    sobre_estadia_planta: Decimal | None = Field(None, alias="Sobre Estadía Planta ($)")
    hora_llegada_puerto: Any | None = Field(None, alias="Hora Llegada Puerto")
    hora_salida_puerto: Any | None = Field(None, alias="Hora Salida Puerto")
    horas_sobre_estadia_puerto: Any | None = Field(None, alias="Horas Sobre Estadía Puerto")
    sobre_estadia_puerto: Decimal | None = Field(None, alias="Sobre Estadía Puerto ($)")
    fecha_gate_in: str | None = Field(None, alias="Fecha Gate In")
    fecha_gate_out: str | None = Field(None, alias="Fecha Gate Out")
    total_servicio: Decimal = Field(Decimal("0"), alias="Total Servicio ($)")
    observaciones: str | None = Field(None, alias="Observaciones")


class OfficialFormatExtractor:
    """Extractor para formato oficial: celdas fijas + datos tabulares.

    Usa Pandas con engine='calamine' (si disponible) para máxima velocidad.
    """

    FIXED_CELLS = {
        "B6": "empresa_transporte",
        "B7": "fecha_emision",
        "B8": "numero_factura",
        "H6": "nave",
        "H7": "puerto_embarque",
        "F4": "responsable",  # Tiene "Aprobado por: " prefix
    }

    def __init__(self, config: ExcelConfig) -> None:
        self._config = config
        self._source_sheet = config.source_sheet
        self.validation_errors: list[dict] = []

    def extract(self, file_path: Path) -> list[InvoiceRecord]:
        """Extrae registros del archivo con formato oficial o formato simple tabular."""
        self.validation_errors = []
        try:
            fixed = self._read_fixed_cells(file_path)

            is_mixed_format = (
                fixed.numero_factura is not None and fixed.empresa_transporte is not None
            )

            if is_mixed_format:
                return self._extract_mixed_format(file_path, fixed)
            else:
                return self._extract_simple_tabular(file_path)

        except Exception as e:
            logger.error("extraction_failed", file=file_path.name, error=str(e))
            raise

    def _extract_mixed_format(self, file_path: Path, fixed: FixedCells) -> list[InvoiceRecord]:
        """Extrae registros usando formato mixto (celdas fijas + tabular)."""
        df = self._read_with_engine(file_path)

        # Validar que las celdas clave tienen valores no nulos
        if (
            not fixed.numero_factura
            or not fixed.numero_factura.strip()
            or not fixed.empresa_transporte
            or not fixed.empresa_transporte.strip()
        ):
            raise SchemaValidationError(
                missing_columns=["N° Factura", "Empresa Transporte"],
                extra_columns=[],
            )

        records = []
        for idx, row in df.iterrows():
            try:
                if row.isna().all():
                    continue

                row_dict = row.to_dict()
                tabular = TabularRow.model_validate(row_dict)

                total = self._calculate_total(tabular)

                record = InvoiceRecord(
                    invoice_number=str(fixed.numero_factura),
                    reference_number=tabular.ordenes_embarque or "N/A",
                    carrier_name=str(fixed.empresa_transporte),
                    invoice_date=self._parse_date(fixed.fecha_emision),
                    description=self._build_description(tabular, fixed),
                    net_amount=total,
                    tax_amount=Decimal("0"),
                    total_amount=total,
                    currency="CLP",
                    source_file=file_path.name,
                )
                records.append(record)

            except ValidationError as e:
                error_msg = f"Validation Error: {str(e)}"
                self.validation_errors.append(
                    {"file": file_path.name, "row_index": int(idx), "error": error_msg}
                )
                logger.warning(
                    "row_validation_failed",
                    file=file_path.name,
                    row=int(idx),
                    errors=e.errors(),
                )
            except Exception as e:
                self.validation_errors.append(
                    {"file": file_path.name, "row_index": int(idx), "error": str(e)}
                )
                logger.warning(
                    "row_extraction_failed",
                    file=file_path.name,
                    row=int(idx),
                    error=str(e),
                )

        logger.info(
            "official_format_extracted",
            file=file_path.name,
            records_found=len(records),
            numero_factura=fixed.numero_factura,
            empresa=fixed.empresa_transporte,
        )

        if not records:
            raise SchemaValidationError(
                missing_columns=["datos tabulares válidos"],
                extra_columns=[],
            )

        return records

    def _extract_simple_tabular(self, file_path: Path) -> list[InvoiceRecord]:
        """Extrae registros usando formato tabular simple (para tests/compatibilidad)."""
        df = self._read_tabular_data(file_path)

        records = []
        for idx, row in df.iterrows():
            try:
                if row.isna().all():
                    continue

                invoice_number = str(row.get("N° Factura", ""))
                if not invoice_number:
                    continue

                total_val = row.get("Monto Total", 0)
                net_val = row.get("Monto Neto", 0)
                tax_val = row.get("IVA", 0)

                def to_decimal(val):
                    if val is None or (isinstance(val, float) and (val != val)):
                        return Decimal("0")
                    return Decimal(str(val))

                total = to_decimal(total_val)
                net = to_decimal(net_val)
                tax = to_decimal(tax_val)

                record = InvoiceRecord(
                    invoice_number=invoice_number,
                    reference_number=str(row.get("N° Referencia")) or "N/A",
                    carrier_name=str(row.get("Transportista", "")),
                    invoice_date=self._parse_date(row.get("Fecha Factura")),
                    description=str(row.get("Descripción", "")),
                    net_amount=net,
                    tax_amount=tax,
                    total_amount=total,
                    currency=str(row.get("Moneda", "CLP")),
                    source_file=file_path.name,
                )
                records.append(record)

            except Exception as e:
                self.validation_errors.append(
                    {"file": file_path.name, "row_index": int(idx), "error": str(e)}
                )
                logger.warning(
                    "row_extraction_failed",
                    file=file_path.name,
                    row=int(idx),
                    error=str(e),
                )

        logger.info(
            "simple_tabular_extracted",
            file=file_path.name,
            records_found=len(records),
        )

        return records

    def _read_tabular_data(self, file_path: Path) -> pd.DataFrame:
        """Lee datos tabulares saltando 10 filas para coincidir con formato oficial."""
        try:
            import fastexcel

            reader = fastexcel.read_excel(file_path)
            df = reader.load_sheet_by_name(self._source_sheet).to_pandas()
            # Saltar 10 filas de encabezados
            df = df.iloc[10:] if len(df) > 10 else df
            # Usar la fila 11 como header
            df.columns = df.iloc[0].astype(str).tolist() if len(df) > 0 else df.columns.tolist()
            df = df[1:].reset_index(drop=True)
            return df
        except Exception:
            df = pd.read_excel(
                file_path,
                sheet_name=self._source_sheet,
                engine="openpyxl",
                header=None,
                skiprows=10,
            )
            # Asignar nombres de columnas desde fila 11
            df.columns = df.iloc[0].astype(str).tolist() if len(df) > 0 else df.columns.tolist()
            df = df[1:].reset_index(drop=True)
            return df

    def _read_with_engine(self, file_path: Path) -> pd.DataFrame:
        """Lee el archivo usando el mejor engine disponible."""
        # Intentar con calamine primero (más rápido)
        try:
            import fastexcel

            # fastexcel lee todo como string para evitar problemas de tipos
            reader = fastexcel.read_excel(file_path)
            # API de fastexcel: load_sheet_by_name
            df = reader.load_sheet_by_name(self._source_sheet).to_pandas()
            # Saltar filas de encabezados fijos (1-10) y la fila de columnas (11)
            df = df.iloc[11:] if len(df) > 11 else df
            df = df.reset_index(drop=True)
            logger.debug("used_fastexcel_engine")
            return df
        except ImportError:
            pass
        except Exception as e:
            logger.warning("fastexcel_failed", error=str(e))

        # Fallback a pandas con calamine engine si está instalado
        try:
            df = pd.read_excel(
                file_path,
                sheet_name=self._source_sheet,
                engine="calamine",
                header=None,  # No usar header automático
                skiprows=10,  # Saltar filas 1-10 (encabezados fijos)
            )
            # Asignar nombres de columnas desde fila 11 (ahora es la primera fila del DF)
            df.columns = df.iloc[0].astype(str).tolist() if len(df) > 0 else df.columns.tolist()
            df = df[1:].reset_index(drop=True)
            logger.debug("used_pandas_calamine_engine")
            return df
        except (ImportError, ValueError):
            pass

        # Último fallback: openpyxl (más lento pero siempre disponible)
        df = pd.read_excel(
            file_path,
            sheet_name=self._source_sheet,
            engine="openpyxl",
            header=None,
            skiprows=10,
        )
        # Asignar nombres de columnas desde fila 11
        df.columns = df.iloc[0].astype(str).tolist() if len(df) > 0 else df.columns.tolist()
        df = df[1:].reset_index(drop=True)
        logger.debug("used_openpyxl_engine")
        return df

    def _read_fixed_cells(self, file_path: Path) -> FixedCells:
        """Lee las celdas fijas usando openpyxl."""
        from openpyxl import load_workbook

        wb = load_workbook(file_path, data_only=True)
        ws = wb[self._source_sheet]

        def _to_str(val: Any) -> str | None:
            if val is None:
                return None
            return str(val)

        cells = {
            "B6": _to_str(ws["B6"].value),
            "B7": _to_str(ws["B7"].value),
            "B8": _to_str(ws["B8"].value),
            "H6": _to_str(ws["H6"].value),
            "H7": _to_str(ws["H7"].value),
            "F4": _to_str(ws["F4"].value),
        }

        return FixedCells.model_validate(cells)

    def _calculate_total(self, row: TabularRow) -> Decimal:
        """Calcula el total sumando todos los componentes monetarios."""
        components = [
            row.flete or Decimal("0"),
            row.underslung or Decimal("0"),
            row.planta_adicional or Decimal("0"),
            row.retiro_cruzado or Decimal("0"),
            row.porteo or Decimal("0"),
            row.sobre_estadia_planta or Decimal("0"),
            row.sobre_estadia_puerto or Decimal("0"),
        ]

        # Si hay un total explícito, usarlo; si no, sumar componentes
        if row.total_servicio and row.total_servicio > 0:
            return row.total_servicio

        return sum(components, Decimal("0"))

    def _build_description(self, row: TabularRow, fixed: FixedCells) -> str:
        """Construye descripción completa con datos operativos."""
        parts = []

        if row.contenedor:
            parts.append(f"Cont: {row.contenedor}")
        if row.unidad:
            parts.append(f"Unidad: {row.unidad}")
        if row.conductor:
            parts.append(f"Conductor: {row.conductor}")
        if fixed.nave:
            parts.append(f"Nave: {fixed.nave}")
        if row.plantas:
            parts.append(f"Planta: {row.plantas}")
        if row.observaciones:
            parts.append(f"Obs: {row.observaciones}")

        return " | ".join(parts) if parts else ""

    def _parse_date(self, value: str | None) -> date:
        """Parsea fecha desde formato dd-mm-yyyy."""
        if not value:
            raise ValueError("Date value is empty or None")

        value = str(value).strip()

        formats = ["%d-%m-%Y", "%d-%m-%y", "%Y-%m-%d"]
        for fmt in formats:
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue

        # Si no se puede parsear, lanzar ValueError
        raise ValueError(f"Formato de fecha inválido: {value}")
