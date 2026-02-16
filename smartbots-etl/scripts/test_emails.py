"""Envía emails de prueba de cada tipo de notificación ETL.

Usage:
    python scripts/test_emails.py

Envía 4 emails de prueba:
    1. SUCCESS - Consolidación exitosa
    2. PARTIAL - Consolidación parcial con errores
    3. ERROR - Error en consolidación
    4. NO_FILES - Sin archivos para procesar
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog
from datetime import UTC, datetime
from decimal import Decimal

from src.application.config import load_config
from src.application.dtos import ExecutionReport
from src.infrastructure.oauth_gmail_notifier import OAuthGmailNotifier
from src.infrastructure.logging_config import setup_logging


def create_success_report() -> ExecutionReport:
    report = ExecutionReport(run_id="test-success-12345678")
    report.status = "SUCCESS"
    report.timestamp = datetime.now(UTC)
    report.source_files = ["Factura_Transporte_01.xlsx", "Factura_Transporte_02.xlsx"]
    report.total_files = 2
    report.source_row_count = 15
    report.valid_row_count = 15
    report.inserted_count = 10
    report.updated_count = 3
    report.unchanged_count = 2
    report.source_total_amount = Decimal("2450000")
    report.output_total_amount = Decimal("2450000")
    report.consolidated_file_id = "1ABC123DEF456GHI789JKL"
    return report


def create_partial_report() -> ExecutionReport:
    report = ExecutionReport(run_id="test-partial-12345678")
    report.status = "PARTIAL"
    report.timestamp = datetime.now(UTC)
    report.source_files = ["Factura_Transporte_01.xlsx", "Factura_Transporte_02.xlsx"]
    report.files_with_errors = ["Factura_Transporte_02.xlsx"]
    report.total_files = 2
    report.source_row_count = 15
    report.valid_row_count = 10
    report.inserted_count = 8
    report.updated_count = 2
    report.unchanged_count = 0
    report.error_count = 5
    report.source_total_amount = Decimal("1800000")
    report.output_total_amount = Decimal("1800000")
    report.consolidated_file_id = "1ABC123DEF456GHI789JKL"
    report.validation_errors = [
        {"file": "Factura_Transporte_02.xlsx", "row_index": 5, "error": "Fecha inválida"},
        {"file": "Factura_Transporte_02.xlsx", "row_index": 8, "error": "Monto negativo"},
        {"file": "Factura_Transporte_02.xlsx", "row_index": 12, "error": "N° Factura vacío"},
    ]
    return report


def create_error_report() -> ExecutionReport:
    """Crea un report de ejemplo para ERROR."""
    report = ExecutionReport(run_id="test-error-12345678")
    report.status = "ERROR"
    report.timestamp = datetime.now(UTC)
    report.source_files = ["Factura_Transporte_01.xlsx"]
    report.files_with_errors = ["Factura_Transporte_01.xlsx"]
    report.total_files = 1
    report.source_row_count = 0
    report.valid_row_count = 0
    report.inserted_count = 0
    report.updated_count = 0
    report.unchanged_count = 0
    report.error_count = 1
    report.source_total_amount = Decimal("0")
    report.output_total_amount = Decimal("0")
    report.validation_errors = [
        {
            "file": "Factura_Transporte_01.xlsx",
            "row_index": "N/A",
            "error": "SchemaValidationError: Columna 'Órdenes de Embarque' no encontrada",
        },
    ]
    report.rollback_executed = True
    return report


def create_no_files_report() -> ExecutionReport:
    """Crea un report de ejemplo para NO_FILES."""
    report = ExecutionReport(run_id="test-nofiles-12345678")
    report.status = "NO_FILES"
    report.timestamp = datetime.now(UTC)
    report.source_files = []
    report.total_files = 0
    report.source_row_count = 0
    report.valid_row_count = 0
    report.inserted_count = 0
    report.updated_count = 0
    report.unchanged_count = 0
    report.source_total_amount = Decimal("0")
    report.output_total_amount = Decimal("0")
    return report


def main() -> int:
    setup_logging(log_level="INFO")
    logger = structlog.get_logger()

    # Cargar configuración
    config = load_config("configs/configuration.yaml")

    # Inicializar notificador
    notifier = OAuthGmailNotifier(
        credentials_path=config.google.credentials_path,
        token_path="credentials/token.json",
        sender=config.email.sender,
        templates_dir=Path("src/templates"),
    )

    # Mapeo de tipos de email
    email_tests = [
        ("SUCCESS", create_success_report, "ETL_Consolidacion_Exito.html"),
        ("PARTIAL", create_partial_report, "ETL_Consolidacion_Parcial.html"),
        ("ERROR", create_error_report, "ETL_Consolidacion_Error.html"),
        ("NO_FILES", create_no_files_report, "ETL_Consolidacion_Vacio.html"),
    ]

    print("=" * 60)
    print("ENVÍO DE EMAILS DE PRUEBA")
    print("=" * 60)
    print(f"Destinatarios: {list(config.email.to)}")
    print(f"CC: {list(config.email.cc)}")
    print(f"Remitente: {config.email.sender}")
    print("=" * 60)

    for status, report_factory, template in email_tests:
        report = report_factory()
        subject = f"{config.email.subject_prefix} TEST [{status}] — {report.run_id[:8]}"

        print(f"\n→ Enviando email [{status}]...")
        print(f"   Template: {template}")
        print(f"   Subject: {subject}")

        try:
            notifier.send(
                subject=subject,
                template_name=template,
                template_vars=report.to_template_vars(),
                recipients=list(config.email.to),
                cc=list(config.email.cc) or None,
            )
            print(f"   ✓ Email enviado correctamente")
        except Exception as e:
            print(f"   ✗ Error: {e}")
            logger.error("email_test_failed", status=status, error=str(e))

    print("\n" + "=" * 60)
    print("FIN DE PRUEBAS")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
