from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation

from src.domain.entities import InvoiceRecord
from src.application.config import ExcelConfig


class RowTransformer:
    def __init__(self, config: ExcelConfig) -> None:
        self.config = config
        self.column_map = config.column_mapping

    def transform_row(self, row: dict, source_name: str) -> InvoiceRecord:
        mapped = self._apply_column_mapping(row)

        total = self._parse_money(mapped.get("total_amount", 0))
        net = self._parse_money(mapped.get("net_amount", total))
        tax = self._parse_money(mapped.get("tax_amount", Decimal("0")))

        return InvoiceRecord(
            invoice_number=self._clean_string(mapped["invoice_number"]),
            reference_number=self._clean_string(mapped["reference_number"]),
            carrier_name=self._clean_string(mapped["carrier_name"]),
            ship_name=self._clean_string(mapped.get("ship_name", "")),
            dispatch_guides=self._clean_string(mapped.get("dispatch_guides", "")),
            invoice_date=self._parse_date(mapped["invoice_date"]),
            description=self._clean_string(mapped.get("description", "")),
            net_amount=net,
            tax_amount=tax,
            total_amount=total,
            currency=self._clean_string(mapped.get("currency", "CLP")).upper(),
            fecha_recepcion_digital=self._clean_string(mapped.get("fecha_recepcion_digital", "")),
            aprobado_por=self._clean_string(mapped.get("aprobado_por", "")),
            estado_operaciones=self._clean_string(mapped.get("estado_operaciones", "")),
            fecha_aprobacion_operaciones=self._clean_string(
                mapped.get("fecha_aprobacion_operaciones", "")
            ),
            source_file=source_name,
            processed_at=datetime.now(UTC),
        )

    def _apply_column_mapping(self, row: dict) -> dict:
        result = {}
        for original_col, standard_name in self.column_map.items():
            if original_col in row:
                result[standard_name] = row[original_col]
            elif standard_name in row:
                result[standard_name] = row[standard_name]
        return result

    @staticmethod
    def _clean_string(value: object) -> str:
        if value is None:
            return ""
        return str(value).strip()

    def _parse_date(self, value: object) -> date:
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        s = str(value).strip()
        for fmt in [self.config.date_format, "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"]:
            try:
                return datetime.strptime(s, fmt).date()
            except ValueError:
                continue
        raise ValueError(f"Formato de fecha no reconocido: '{value}'")

    @staticmethod
    def _parse_money(value: object) -> Decimal:
        if isinstance(value, Decimal):
            return value
        if isinstance(value, (int, float)):
            return Decimal(str(value))
        s = str(value).strip()
        # Remove currency symbols and whitespace
        s = s.replace("$", "").replace(" ", "")
        # Detect Chilean format (1.234.567) vs US format (1,234.56)
        if "." in s and "," in s:
            if s.rindex(".") > s.rindex(","):
                # 1,234.56 — US format
                s = s.replace(",", "")
            else:
                # 1.234,56 — Chilean/European format
                s = s.replace(".", "").replace(",", ".")
        elif "," in s and s.count(",") == 1:
            # Could be decimal: 1234,56
            s = s.replace(",", ".")
        elif "." in s and s.count(".") > 1:
            # Multiple dots = thousands separators: 1.234.567
            s = s.replace(".", "")
        elif "." in s and s.count(".") == 1:
            # Single dot with exactly 3 trailing digits = Chilean thousands (12.345 → 12345)
            parts = s.split(".")
            if len(parts[1]) == 3:
                s = s.replace(".", "")
        try:
            return Decimal(s)
        except InvalidOperation as e:
            raise ValueError(f"Monto inválido: '{value}'") from e
