"""Entry point for the invoice consolidation process.

Usage:
    python scripts/run_consolidation.py [path/to/config.yaml]

Flujo de ejecución:
    1. Carga configuración desde YAML
    2. Inicializa adaptadores (Google Drive, Gmail, SQLite)
    3. Ejecuta ConsolidateInvoicesUseCase que:
        a) Lista archivos en carpeta source de Drive
        b) Descarga cada archivo Excel
        c) Extrae datos usando OfficialFormatExtractor
        d) Lee archivo consolidado
        e) hace upsert de registros
        f) Actualiza archivo consolidado en Drive
        g) Mueve archivo origen a carpeta Respaldo
    4. Envía notificación por email
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog

from src.application.config import load_config
from src.infrastructure.logging_config import setup_logging
from src.infrastructure.oauth_google_drive_adapter import OAuthGoogleDriveAdapter
from src.infrastructure.excel_handler import OpenpyxlExcelHandler
from src.infrastructure.oauth_gmail_notifier import OAuthGmailNotifier
from src.infrastructure.sqlite_tracker import SqliteTracker
from src.infrastructure.drive_path_resolver import DrivePathResolver
from src.infrastructure.file_lifecycle_manager import FileLifecycleManager
from src.application.use_cases.consolidate_invoices import ConsolidateInvoicesUseCase

def clear_screen():
    import os
    import subprocess
    if os.name == 'nt':
        subprocess.run([r"C:\\Windows\\System32\\cmd.exe", "/c", "cls"])
    else:
        from shutil import which
        clear_cmd = which("clear")
        if clear_cmd:
            subprocess.run([clear_cmd])
        else:
            print("\033c", end="")  # fallback: ANSI clear screen

def main() -> int:
    # 0. Limpiar pantalla al inicio
    clear_screen()

    # 1. Cargar configuración desde archivo YAML
    config_path = sys.argv[1] if len(sys.argv) > 1 else "configs/configuration.yaml"
    config = load_config(config_path)

    # 2. Configurar logging
    setup_logging(
        log_level=config.logging.level,
        log_dir=Path(config.logging.log_dir) if config.logging.log_to_file else None,
    )
    logger = structlog.get_logger()
    logger.info("consolidation_starting", config_path=config_path)

    # 3. Inicializar adaptador de Google Drive (OAuth)
    drive = OAuthGoogleDriveAdapter(
        credentials_path=config.google.credentials_path,
        token_path="credentials/token.json",
        shared_drive_id=None,
    )

    # 4. Inicializar resolvedor de rutas de Drive
    path_resolver = DrivePathResolver(drive.service, None)
    # 5. Inicializar gestor de ciclo de vida de archivos
    lifecycle = FileLifecycleManager(
        drive_service=drive.service,
        path_resolver=path_resolver,
        config=config.drive,
        shared_drive_id=None,
    )
    # 6. Inicializar handler de Excel (openpyxl)
    excel = OpenpyxlExcelHandler()
    # 7. Inicializar notificador de Gmail
    notifier = OAuthGmailNotifier(
        credentials_path=config.google.credentials_path,
        token_path="credentials/token.json",
        sender=config.email.sender,
        templates_dir=Path("src/templates"),
    )
    # 8. Inicializar tracker de SQLite
    tracker = SqliteTracker(db_path=config.tracking.db_path)

    try:
        # 9. Crear y ejecutar el caso de uso de consolidación
        #    → Ir a consolidate_invoices.py para ver el flujo completo
        use_case = ConsolidateInvoicesUseCase(
            drive=drive,
            reader=excel,
            writer=excel,
            notifier=notifier,
            tracker=tracker,
            config=config,
            path_resolver=path_resolver,
            lifecycle=lifecycle,
        )
        # 10. Ejecutar consolidación
        #     → Flujo en consolidate_invoices.py:
        #       - Lista archivos en carpeta source de Drive
        #       - Descarga cada archivo Excel
        #       - Extrae datos usando OfficialFormatExtractor (src/infrastructure/official_format_extractor.py)
        #       - Lee archivo consolidado
        #       - Hace upsert de registros
        #       - Actualiza archivo consolidado en Drive
        #       - Mueve archivo origen a carpeta Respaldo
        report = use_case.execute()
        logger.info(
            "consolidation_finished",
            status=report.status,
            inserted=report.inserted_count,
            updated=report.updated_count,
            errors=report.error_count,
        )
        return 0 if not report.has_errors else 1
    finally:
        tracker.close()


if __name__ == "__main__":
    sys.exit(main())