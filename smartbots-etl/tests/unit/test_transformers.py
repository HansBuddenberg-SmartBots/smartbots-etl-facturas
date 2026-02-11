from decimal import Decimal
from datetime import date

import pytest

from src.application.transformers import RowTransformer
from src.application.config import ExcelConfig


@pytest.fixture
def transformer():
    config = ExcelConfig()
    return RowTransformer(config)


class TestMoneyParsing:
    def test_parses_chilean_format(self, transformer):
        assert transformer._parse_money("1.234.567") == Decimal("1234567")

    def test_parses_with_dollar_sign(self, transformer):
        assert transformer._parse_money("$12.345") == Decimal("12345")

    def test_parses_decimal_comma(self, transformer):
        assert transformer._parse_money("1234,56") == Decimal("1234.56")

    def test_parses_us_format(self, transformer):
        assert transformer._parse_money("1,234.56") == Decimal("1234.56")

    def test_parses_integer(self, transformer):
        assert transformer._parse_money(50000) == Decimal("50000")

    def test_parses_float(self, transformer):
        assert transformer._parse_money(123.45) == Decimal("123.45")

    def test_parses_decimal_passthrough(self, transformer):
        d = Decimal("999")
        assert transformer._parse_money(d) is d

    def test_rejects_invalid(self, transformer):
        with pytest.raises(ValueError, match="Monto inválido"):
            transformer._parse_money("N/A")

    def test_parses_european_format(self, transformer):
        assert transformer._parse_money("1.234,56") == Decimal("1234.56")

    def test_parses_plain_number_string(self, transformer):
        assert transformer._parse_money("50000") == Decimal("50000")


class TestDateParsing:
    def test_parses_chilean_format(self, transformer):
        assert transformer._parse_date("15-02-2026") == date(2026, 2, 15)

    def test_parses_iso_format(self, transformer):
        assert transformer._parse_date("2026-02-15") == date(2026, 2, 15)

    def test_parses_slash_format(self, transformer):
        assert transformer._parse_date("15/02/2026") == date(2026, 2, 15)

    def test_passes_through_date_object(self, transformer):
        d = date(2026, 1, 1)
        assert transformer._parse_date(d) == d

    def test_rejects_invalid(self, transformer):
        with pytest.raises(ValueError, match="Formato de fecha"):
            transformer._parse_date("31-13-2026")


class TestRowTransform:
    def test_transforms_complete_row(self, transformer):
        row = {
            "N° Factura": "F-100",
            "N° Referencia": "GD-200",
            "Transportista": "  Beta  ",
            "Fecha Factura": "15-02-2026",
            "Descripción": "Transporte",
            "Monto Neto": "10000",
            "IVA": "1900",
            "Monto Total": "11900",
            "Moneda": "clp",
        }
        record = transformer.transform_row(row, "test.xlsx")
        assert record.invoice_number == "F-100"
        assert record.carrier_name == "Beta"
        assert record.currency == "CLP"
        assert record.net_amount == Decimal("10000")
        assert record.source_file == "test.xlsx"
