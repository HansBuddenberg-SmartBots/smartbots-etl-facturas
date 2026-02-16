from decimal import Decimal
from datetime import date

import pytest

from src.domain.entities import InvoiceRecord, RecordStatus


def _make_record(**overrides) -> InvoiceRecord:
    defaults = {
        "invoice_number": "F-001",
        "reference_number": "GD-100",
        "carrier_name": "Alfa",
        "ship_name": "Nave Alpha",
        "dispatch_guides": "GD-001",
        "invoice_date": date(2026, 2, 1),
        "description": "Servicio",
        "net_amount": Decimal("10000"),
        "tax_amount": Decimal("1900"),
        "total_amount": Decimal("11900"),
    }
    defaults.update(overrides)
    return InvoiceRecord(**defaults)


class TestInvoiceRecord:
    def test_primary_key_composite(self):
        record = _make_record()
        assert record.primary_key == ("F-001", "GD-100")

    def test_rejects_negative_total(self):
        with pytest.raises(ValueError, match="no puede ser negativo"):
            _make_record(
                net_amount=Decimal("-100"),
                tax_amount=Decimal("0"),
                total_amount=Decimal("-100"),
            )

    def test_validates_total_equals_net_plus_tax(self):
        with pytest.raises(ValueError, match="no coincide"):
            _make_record(total_amount=Decimal("15000"))

    def test_detects_changes(self):
        a = _make_record()
        b = _make_record(
            net_amount=Decimal("12000"),
            tax_amount=Decimal("2280"),
            total_amount=Decimal("14280"),
        )
        assert a.has_changes_vs(b) is True

    def test_detects_no_changes(self):
        a = _make_record()
        b = _make_record(description="Otro texto")
        assert a.has_changes_vs(b) is False

    def test_immutability(self):
        record = _make_record()
        with pytest.raises(AttributeError):
            record.total_amount = Decimal("99999")  # type: ignore[misc]

    def test_rejects_empty_invoice_number(self):
        with pytest.raises(ValueError, match="invoice_number"):
            _make_record(invoice_number="  ")

    def test_rejects_empty_reference_number(self):
        with pytest.raises(ValueError, match="reference_number"):
            _make_record(reference_number="")

    def test_with_status_returns_new_instance(self):
        original = _make_record()
        updated = original.with_status(RecordStatus.UPDATED)
        assert updated.status == RecordStatus.UPDATED
        assert original.status == RecordStatus.NEW
        assert updated.primary_key == original.primary_key

    def test_total_tolerance_within_one(self):
        # total_amount differs from net+tax by exactly 1 — should pass
        record = _make_record(
            net_amount=Decimal("10000"),
            tax_amount=Decimal("1900"),
            total_amount=Decimal("11901"),
        )
        assert record.total_amount == Decimal("11901")

    def test_total_tolerance_beyond_one_fails(self):
        with pytest.raises(ValueError, match="no coincide"):
            _make_record(
                net_amount=Decimal("10000"),
                tax_amount=Decimal("1900"),
                total_amount=Decimal("11902"),
            )
