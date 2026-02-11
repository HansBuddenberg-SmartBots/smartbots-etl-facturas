"""Entry point for the invoice consolidation process.

Usage:
    python scripts/run_consolidation.py [path/to/config.yaml]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog

from src.application.config import load_config
from src.infrastructure.logging_config import setup_logging
from src.infrastructure.google_drive_adapter import GoogleDriveAdapter
from src.infrastructure.excel_handler import OpenpyxlExcelHandler
from src.infrastructure.gmail_notifier import GmailNotifier
from src.infrastructure.sqlite_tracker import SqliteTracker
from src.infrastructure.drive_path_resolver import DrivePathResolver
from src.infrastructure.file_lifecycle_manager import FileLifecycleManager
from src.application.use_cases.consolidate_invoices import ConsolidateInvoicesUseCase


def main() -> int:
    config_path = sys.argv[1] if len(sys.argv) > 1 else "configs/configuration.yaml"
    config = load_config(config_path)

    setup_logging(
        log_level=config.logging.level,
        log_dir=Path(config.logging.log_dir) if config.logging.log_to_file else None,
    )
    logger = structlog.get_logger()
    logger.info("consolidation_starting", config_path=config_path)

    drive = GoogleDriveAdapter(credentials_path=config.google.credentials_path)

    shared_drive_id = (
        DrivePathResolver.detect_shared_drive(drive.service, config.google.shared_drive_name)
        if config.google.shared_drive_name
        else None
    )

    if shared_drive_id:
        drive = GoogleDriveAdapter(
            credentials_path=config.google.credentials_path,
            shared_drive_id=shared_drive_id,
        )

    path_resolver = DrivePathResolver(drive.service, shared_drive_id)
    lifecycle = FileLifecycleManager(
        drive_service=drive.service,
        path_resolver=path_resolver,
        config=config.drive,
        shared_drive_id=shared_drive_id,
    )
    excel = OpenpyxlExcelHandler()
    notifier = GmailNotifier(
        credentials_path=config.google.credentials_path,
        delegated_user=config.google.delegated_user,
        sender=config.email.sender,
        templates_dir=Path("src/templates"),
    )
    tracker = SqliteTracker(db_path=config.tracking.db_path)

    try:
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
