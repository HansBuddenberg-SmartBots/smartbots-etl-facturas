"""Integration tests: real UseCase + SqliteTracker + ExcelHandler + RowTransformer.

Only the Google API boundary (Drive, Notifier, PathResolver, Lifecycle) is faked.
"""

from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from tests.integration.conftest import (
    create_consolidated_xlsx,
    create_source_xlsx,
)


def _valid_source_rows() -> list[dict]:
    return [
        {
            "N° Factura": "FAC-001",
            "N° Referencia": "REF-001",
            "Transportista": "Transportes Chile Ltda",
            "Fecha Factura": "15-01-2026",
            "Descripción": "Flete Santiago-Valparaíso",
            "Monto Neto": 100000,
            "IVA": 19000,
            "Monto Total": 119000,
            "Moneda": "CLP",
        },
        {
            "N° Factura": "FAC-002",
            "N° Referencia": "REF-002",
            "Transportista": "Logística Sur S.A.",
            "Fecha Factura": "16-01-2026",
            "Descripción": "Flete Concepción-Temuco",
            "Monto Neto": 200000,
            "IVA": 38000,
            "Monto Total": 238000,
            "Moneda": "CLP",
        },
        {
            "N° Factura": "FAC-003",
            "N° Referencia": "REF-003",
            "Transportista": "Carga Rápida SpA",
            "Fecha Factura": "17-01-2026",
            "Descripción": "Flete Antofagasta-Iquique",
            "Monto Neto": 150000,
            "IVA": 28500,
            "Monto Total": 178500,
            "Moneda": "CLP",
        },
    ]


def _valid_mixed_format_fixed_cells() -> dict:
    return {
        "empresa_transporte": "Transportes Chile Ltda",
        "fecha_emision": "15-01-2026",
        "numero_factura": "FAC-001",
        "nave": "MSC GÜLSÜN",
        "puerto_embarque": "San Antonio",
        "aprobado_por": "Aprobado por: Juan Pérez",
    }


def _valid_mixed_format_tabular_rows() -> list[dict]:
    return [
        {
            "Fecha Servicio": "15-01-2026",
            "Unidad": "ABC123",
            "Conductor": "Pedro García",
            "Contenedor": "MSCU1234567",
            "Patente Camión": "AB1234",
            "Patente Carro": "CD5678",
            "Órdenes de Embarque": "OE-001",
            "Plantas": "Planta Norte",
            "Guías de Despacho": "GD-001",
            "Cantidad Pallets": 10,
            "Flete($)": 100000,
            "Underslung($)": 0,
            "Planta Adicional ($)": 0,
            "Retiro Cruzado ($)": 0,
            "Porteo($)": 0,
            "Hora Llegada Planta": "08:00",
            "Hora Salida Planta": "10:00",
            "Horas Sobre Estadía Planta": 0,
            "Sobre Estadía Planta ($)": 0,
            "Hora Llegada Puerto": "12:00",
            "Hora Salida Puerto": "14:00",
            "Horas Sobre Estadía Puerto": 0,
            "Sobre Estadía Puerto ($)": 0,
            "Fecha Gate In": "15-01-2026",
            "Fecha Gate Out": "16-01-2026",
            "Total Servicio ($)": 100000,
        },
        {
            "Fecha Servicio": "16-01-2026",
            "Unidad": "DEF456",
            "Conductor": "María López",
            "Contenedor": "MSCU7654321",
            "Patente Camión": "EF9012",
            "Patente Carro": "GH3456",
            "Órdenes de Embarque": "OE-002",
            "Plantas": "Planta Sur",
            "Guías de Despacho": "GD-002",
            "Cantidad Pallets": 20,
            "Flete($)": 200000,
            "Underslung($)": 0,
            "Planta Adicional ($)": 0,
            "Retiro Cruzado ($)": 0,
            "Porteo($)": 0,
            "Hora Llegada Planta": "09:00",
            "Hora Salida Planta": "11:00",
            "Horas Sobre Estadía Planta": 0,
            "Sobre Estadía Planta ($)": 0,
            "Hora Llegada Puerto": "13:00",
            "Hora Salida Puerto": "15:00",
            "Horas Sobre Estadía Puerto": 0,
            "Sobre Estadía Puerto ($)": 0,
            "Fecha Gate In": "16-01-2026",
            "Fecha Gate Out": "17-01-2026",
            "Total Servicio ($)": 200000,
        },
        {
            "Fecha Servicio": "17-01-2026",
            "Unidad": "GHI789",
            "Conductor": "Carlos Ruiz",
            "Contenedor": "MSCU1112222",
            "Patente Camión": "IJ7890",
            "Patente Carro": "KL1234",
            "Órdenes de Embarque": "OE-003",
            "Plantas": "Planta Centro",
            "Guías de Despacho": "GD-003",
            "Cantidad Pallets": 15,
            "Flete($)": 150000,
            "Underslung($)": 0,
            "Planta Adicional ($)": 0,
            "Retiro Cruzado ($)": 0,
            "Porteo($)": 0,
            "Hora Llegada Planta": "10:00",
            "Hora Salida Planta": "12:00",
            "Horas Sobre Estadía Planta": 0,
            "Sobre Estadía Planta ($)": 0,
            "Hora Llegada Puerto": "14:00",
            "Hora Salida Puerto": "16:00",
            "Horas Sobre Estadía Puerto": 0,
            "Sobre Estadía Puerto ($)": 0,
            "Fecha Gate In": "17-01-2026",
            "Fecha Gate Out": "18-01-2026",
            "Total Servicio ($)": 150000,
        },
    ]


def _register_source(fake_drive, tmp_path, filename, rows, modified_time=None):
    path = tmp_path / filename
    create_source_xlsx(path, rows)
    file_id = f"src_{filename}"
    fake_drive.register(file_id, path)
    return {
        "file_id": file_id,
        "name": filename,
        "modified_time": modified_time or "2026-01-15T10:00:00Z",
    }


def _register_mixed_source(
    fake_drive, tmp_path, filename, fixed_cells, tabular_rows, modified_time=None
):
    from tests.integration.conftest import create_mixed_format_source_xlsx

    path = tmp_path / filename
    create_mixed_format_source_xlsx(path, fixed_cells, tabular_rows)
    file_id = f"src_{filename}"
    fake_drive.register(file_id, path)
    return {
        "file_id": file_id,
        "name": filename,
        "modified_time": modified_time or "2026-01-15T10:00:00Z",
    }


def _register_consolidated(fake_drive, tmp_path, rows=None):
    path = tmp_path / "consolidado.xlsx"
    create_consolidated_xlsx(path, rows, header_row=11)
    fake_drive.register("consolidated_file_id", path)
    fake_drive.set_find_result("consolidado.xlsx", "consolidated_file_id")
    return path


def _read_result(consolidated_path: Path) -> pd.DataFrame:
    return pd.read_excel(consolidated_path, sheet_name="Consolidado", engine="openpyxl", header=10)


class TestSuccessFreshConsolidation:
    def test_fresh_insert_three_rows(self, tmp_path, fake_drive, fake_notifier, build_use_case):
        sources = [
            _register_mixed_source(
                fake_drive,
                tmp_path,
                "facturas_enero.xlsx",
                _valid_mixed_format_fixed_cells(),
                _valid_mixed_format_tabular_rows(),
            )
        ]
        fake_drive.set_source_files(sources)
        consolidated_path = _register_consolidated(fake_drive, tmp_path)

        report = build_use_case().execute()

        assert report.status == "SUCCESS"
        assert report.inserted_count == 3
        assert report.updated_count == 0
        assert report.unchanged_count == 0
        assert report.total_files == 1
        assert report.source_row_count == 3
        assert report.valid_row_count == 3
        assert not report.files_with_errors
        assert not report.validation_errors

        df = _read_result(consolidated_path)
        assert len(df) == 3
        assert set(df["invoice_number"]) == {"FAC-001"}

        assert len(fake_notifier.calls) == 1
        assert "SUCCESS" in fake_notifier.calls[0]["subject"]


class TestUpsertUpdatesAndPreserves:
    def test_upsert_update_and_insert(self, tmp_path, fake_drive, fake_notifier, build_use_case):
        existing_rows = [
            {
                "invoice_number": "FAC-001",
                "reference_number": "REF-001",
                "carrier_name": "Transportes Chile Ltda",
                "invoice_date": "2026-01-15",
                "description": "Flete Santiago-Valparaíso",
                "net_amount": 100000,
                "tax_amount": 19000,
                "total_amount": 119000,
                "currency": "CLP",
                "source_file": "old_file.xlsx",
            },
            {
                "invoice_number": "FAC-004",
                "reference_number": "REF-004",
                "carrier_name": "Trans Norte Ltda",
                "invoice_date": "2026-01-20",
                "description": "Flete Arica-Santiago",
                "net_amount": 250000,
                "tax_amount": 47500,
                "total_amount": 297500,
                "currency": "CLP",
                "source_file": "old_file.xlsx",
            },
        ]
        consolidated_path = _register_consolidated(fake_drive, tmp_path, existing_rows)

        source_rows = [
            {
                "N° Factura": "FAC-001",
                "N° Referencia": "REF-001",
                "Transportista": "Transportes Chile Ltda",
                "Fecha Factura": "15-01-2026",
                "Descripción": "Flete Santiago-Valparaíso ACTUALIZADO",
                "Monto Neto": 120000,
                "IVA": 22800,
                "Monto Total": 142800,
                "Moneda": "CLP",
            },
            {
                "N° Factura": "FAC-005",
                "N° Referencia": "REF-005",
                "Transportista": "Express Sur SpA",
                "Fecha Factura": "22-01-2026",
                "Descripción": "Flete Talca-Chillán",
                "Monto Neto": 300000,
                "IVA": 57000,
                "Monto Total": 357000,
                "Moneda": "CLP",
            },
        ]
        sources = [_register_source(fake_drive, tmp_path, "facturas_feb.xlsx", source_rows)]
        fake_drive.set_source_files(sources)

        report = build_use_case().execute()

        assert report.status == "SUCCESS"
        assert report.inserted_count == 1
        assert report.updated_count == 1
        assert report.unchanged_count == 0

        df = _read_result(consolidated_path)
        assert len(df) == 3
        assert set(df["invoice_number"]) == {"FAC-001", "FAC-004", "FAC-005"}

        # Append-only behavior: FAC-001 was updated in source, but Excel remains UNTOUCHED
        fac001 = df[df["invoice_number"] == "FAC-001"].iloc[0]
        assert float(fac001["total_amount"]) == 119000.0  # Kept OLD value

        fac004 = df[df["invoice_number"] == "FAC-004"].iloc[0]
        assert float(fac004["total_amount"]) == 297500.0

        fac005 = df[df["invoice_number"] == "FAC-005"].iloc[0]
        assert float(fac005["total_amount"]) == 357000.0


class TestPartialMixedFiles:
    def test_partial_with_schema_error(self, tmp_path, fake_drive, fake_notifier, build_use_case):
        good_meta = _register_source(fake_drive, tmp_path, "good_file.xlsx", _valid_source_rows())

        bad_path = tmp_path / "bad_file.xlsx"
        bad_df = pd.DataFrame({"Columna_Invalida": ["X"], "Otra_Columna": [123]})
        bad_df.to_excel(bad_path, sheet_name="Sheet1", index=False, engine="openpyxl")
        fake_drive.register("src_bad_file.xlsx", bad_path)
        bad_meta = {
            "file_id": "src_bad_file.xlsx",
            "name": "bad_file.xlsx",
            "modified_time": "2026-01-16T10:00:00Z",
        }

        fake_drive.set_source_files([good_meta, bad_meta])
        _register_consolidated(fake_drive, tmp_path)

        report = build_use_case().execute()

        assert report.status == "PARTIAL"
        assert len(report.files_with_errors) == 1
        assert "bad_file.xlsx" in report.files_with_errors
        assert report.inserted_count == 3
        assert report.total_files == 2


class TestTrackerAuditTrail:
    def test_tracker_tables_populated(
        self, tmp_path, fake_drive, fake_notifier, build_use_case, tracker
    ):
        sources = [
            _register_source(fake_drive, tmp_path, "facturas_enero.xlsx", _valid_source_rows())
        ]
        fake_drive.set_source_files(sources)
        _register_consolidated(fake_drive, tmp_path)

        report = build_use_case().execute()

        cursor = tracker._conn.execute(
            "SELECT * FROM execution_runs WHERE run_uuid=?", (report.run_id,)
        )
        run_row = cursor.fetchone()
        columns = [d[0] for d in cursor.description]
        run = dict(zip(columns, run_row))
        assert run["status"] == "SUCCESS"
        assert run["inserted"] == 3
        assert run["total_files"] == 1
        assert run["total_records"] == 3
        assert run["finished_at"] is not None

        cursor = tracker._conn.execute("SELECT * FROM file_log WHERE run_uuid=?", (report.run_id,))
        file_rows = cursor.fetchall()
        columns = [d[0] for d in cursor.description]
        files = [dict(zip(columns, r)) for r in file_rows]
        assert len(files) == 1
        assert files[0]["file_name"] == "facturas_enero.xlsx"
        assert files[0]["schema_valid"] == 1
        assert files[0]["status"] == "COMPLETED"
        assert files[0]["rows_total"] == 3
        assert files[0]["rows_valid"] == 3
        assert files[0]["rows_error"] == 0

        cursor = tracker._conn.execute(
            "SELECT * FROM record_log WHERE run_uuid=?", (report.run_id,)
        )
        rec_rows = cursor.fetchall()
        columns = [d[0] for d in cursor.description]
        records = [dict(zip(columns, r)) for r in rec_rows]
        assert len(records) == 3
        assert {r["action"] for r in records} == {"INSERT"}
        assert {r["invoice_number"] for r in records} == {
            "FAC-001",
            "FAC-002",
            "FAC-003",
        }


class TestRowValidationErrors:
    def test_validation_errors_logged(
        self, tmp_path, fake_drive, fake_notifier, build_use_case, tracker
    ):
        rows = [
            {
                "N° Factura": "FAC-001",
                "N° Referencia": "REF-001",
                "Transportista": "Trans A",
                "Fecha Factura": "15-01-2026",
                "Descripción": "Desc A",
                "Monto Neto": 100000,
                "IVA": 19000,
                "Monto Total": 119000,
                "Moneda": "CLP",
            },
            {
                "N° Factura": "FAC-BAD",
                "N° Referencia": "REF-BAD",
                "Transportista": "Trans B",
                "Fecha Factura": "INVALID-DATE",
                "Descripción": "Desc B",
                "Monto Neto": 50000,
                "IVA": 9500,
                "Monto Total": 59500,
                "Moneda": "CLP",
            },
            {
                "N° Factura": "FAC-003",
                "N° Referencia": "REF-003",
                "Transportista": "Trans C",
                "Fecha Factura": "17-01-2026",
                "Descripción": "Desc C",
                "Monto Neto": 150000,
                "IVA": 28500,
                "Monto Total": 178500,
                "Moneda": "CLP",
            },
        ]
        sources = [_register_source(fake_drive, tmp_path, "mixed.xlsx", rows)]
        fake_drive.set_source_files(sources)
        consolidated_path = _register_consolidated(fake_drive, tmp_path)

        report = build_use_case().execute()

        assert report.status == "SUCCESS"
        assert report.source_row_count == 2
        assert report.valid_row_count == 2
        assert report.inserted_count == 2
        assert len(report.validation_errors) == 1
        assert "fecha" in report.validation_errors[0]["error"].lower()

        cursor = tracker._conn.execute(
            "SELECT action, invoice_number, error_message FROM record_log WHERE run_uuid=?",
            (report.run_id,),
        )
        records = cursor.fetchall()
        actions = [r[0] for r in records]
        assert actions.count("INSERT") == 2
        assert actions.count("VALIDATION_ERROR") == 1

        df = _read_result(consolidated_path)
        assert len(df) == 2


class TestFinancialReconciliation:
    def test_amounts_match(self, tmp_path, fake_drive, fake_notifier, build_use_case):
        sources = [_register_source(fake_drive, tmp_path, "facturas.xlsx", _valid_source_rows())]
        fake_drive.set_source_files(sources)
        _register_consolidated(fake_drive, tmp_path)

        report = build_use_case().execute()

        assert report.status == "SUCCESS"
        assert report.source_total_amount == Decimal("535500")
        assert report.output_total_amount == Decimal("535500")
        assert report.amount_variance == Decimal("0")


class TestNoSourceFiles:
    def test_no_files(self, tmp_path, fake_drive, fake_notifier, build_use_case):
        fake_drive.set_source_files([])
        _register_consolidated(fake_drive, tmp_path)

        report = build_use_case().execute()

        assert report.status == "NO_FILES"
        assert report.total_files == 0
        assert report.inserted_count == 0

        assert len(fake_notifier.calls) == 1
