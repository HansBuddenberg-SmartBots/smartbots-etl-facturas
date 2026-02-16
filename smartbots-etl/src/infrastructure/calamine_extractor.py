"""Extractor rápido usando fastexcel (calamine backend en Rust)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastexcel import read_excel
import structlog

from src.application.config import ExcelConfig
from src.domain.entities import InvoiceRecord
from src.domain.value_objects import Money

logger = structlog.get_logger()


class CalamineExtractor:
    """Extractor usando calamine para lectura rápida de XLSX."""

    def __init__(self, config: ExcelConfig) -> None:
        self._config = config
        self._source_sheet = config.source_sheet

    def extract(self, file_path: Path) -> list[InvoiceRecord]:
        """Extrae registros usando calamine."""
        try:
            # Leer con fastexcel (usa calamine backend)
            excel_reader = read_excel(file_path)

            # Obtener el sheet por nombre
            if self._source_sheet not in excel_reader.sheet_names:
                raise ValueError(
                    f"Sheet '{self._source_sheet}' no encontrado. "
                    f"Disponibles: {excel_reader.sheet_names}"
                )

            df = excel_reader.read_sheet(self._source_sheet, dtype="string")

            records = []
            for idx in range(len(df)):
                try:
                    # Obtener valores de celdas específicas
                    # Formato: B6, B7, B8, H6 (celdas fijas)
                    row_data = df.row(idx)

                    # Extraer usando índices de columnas
                    # Columna B = índice 1, H = índice 7

                    # Buscar fila con datos (no headers)
                    if idx < 10:  # Saltar filas de encabezados
                        continue

                    # Extraer valores
                    empresa = self._get_cell_value(row_data, 1)  # Columna B
                    fecha = self._get_cell_value(row_data, 7)  # Columna H

                    if not empresa or not fecha:
                        continue

                    # Crear InvoiceRecord
                    record = InvoiceRecord(
                        invoice_number=str(idx),
                        reference_number=self._get_cell_value(row_data, 6) or "",
                        carrier_name=str(empresa),
                        ship_name="",
                        dispatch_guides="",
                        invoice_date=self._parse_date(fecha),
                        description="",
                        net_amount=Money(amount="0"),
                        tax_amount=Money(amount="0"),
                        total_amount=Money(amount=self._get_cell_value(row_data, -1) or "0"),
                        currency="CLP",
                        fecha_recepcion_digital="",
                        aprobado_por="",
                        estado_operaciones="",
                        fecha_aprobacion_operaciones="",
                        source_file=file_path.name,
                    )
                    records.append(record)

                except Exception as e:
                    logger.warning("row_extract_failed", file=file_path.name, row=idx, error=str(e))

            logger.info(
                "calamine_extracted",
                file=file_path.name,
                records_found=len(records),
            )
            return records

        except Exception as e:
            logger.error("extraction_failed", file=file_path.name, error=str(e))
            raise

    def _get_cell_value(self, row: list[Any], col_idx: int) -> str | None:
        """Obtiene valor de celda, soporta índices negativos."""
        try:
            if col_idx < 0:
                col_idx = len(row) + col_idx
            val = row[col_idx]
            return str(val).strip() if val and str(val).strip() != "None" else None
        except IndexError:
            return None

    def _parse_date(self, value: str | None) -> str:
        """Parsea fecha desde formato Excel o dd-mm-yyyy."""
        if not value:
            return ""

        from datetime import datetime

        # Intentar varios formatos
        formats = ["%d-%m-%Y", "%Y-%m-%d"]
        for fmt in formats:
            try:
                dt = datetime.strptime(value, fmt)
                return dt.strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                continue

        # Si es número de serie de Excel
        try:
            excel_date = float(value)
            dt = datetime.fromordinal(datetime(1900, 1, 1).toordinal() + int(excel_date) - 2)
            return dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            pass

        return value
