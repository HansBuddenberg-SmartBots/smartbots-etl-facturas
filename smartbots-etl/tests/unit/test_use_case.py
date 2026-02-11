from decimal import Decimal
from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.application.use_cases.consolidate_invoices import ConsolidateInvoicesUseCase
from src.application.config import (
    AppConfig,
    GoogleConfig,
    DrivePathsConfig,
    ExcelConfig,
    EmailConfig,
    TrackingConfig,
    LoggingConfig,
)


@pytest.fixture
def config():
    return AppConfig(
        google=GoogleConfig(credentials_path="/tmp/creds.json"),
        drive=DrivePathsConfig(source_path="Bot RPA/ETL"),
        excel=ExcelConfig(),
        email=EmailConfig(
            sender="etl@test.com",
            to=("dest@test.com",),
            templates={
                "success": "Exito.html",
                "error": "Error.html",
                "partial": "Parcial.html",
                "empty": "Vacio.html",
            },
        ),
        tracking=TrackingConfig(),
        logging=LoggingConfig(),
    )


@pytest.fixture
def mocks():
    return {
        "drive": MagicMock(),
        "reader": MagicMock(),
        "writer": MagicMock(),
        "notifier": MagicMock(),
        "tracker": MagicMock(),
        "path_resolver": MagicMock(),
        "lifecycle": MagicMock(),
    }


class TestConsolidateInvoicesUseCase:
    def test_no_files_returns_no_files_status(self, config, mocks):
        mocks["path_resolver"].resolve_path.return_value = "folder-id"
        mocks["drive"].find_file_in_folder.return_value = "consol-id"
        mocks["drive"].list_source_files.return_value = []

        uc = ConsolidateInvoicesUseCase(**mocks, config=config)
        report = uc.execute()

        assert report.status == "NO_FILES"
        mocks["notifier"].send.assert_called_once()
        mocks["tracker"].start_run.assert_called_once()

    def test_always_sends_notification(self, config, mocks):
        mocks["path_resolver"].resolve_path.side_effect = Exception("boom")

        uc = ConsolidateInvoicesUseCase(**mocks, config=config)
        report = uc.execute()

        assert report.status == "ERROR"
        mocks["notifier"].send.assert_called_once()

    def test_rollback_on_fatal_exception(self, config, mocks):
        mocks["path_resolver"].resolve_path.return_value = "folder-id"
        mocks["drive"].find_file_in_folder.return_value = "consol-id"
        mocks["drive"].list_source_files.return_value = [
            {"file_id": "id-1", "name": "test.xlsx", "modified_time": "2026-01-01"}
        ]
        mocks["drive"].create_backup.return_value = "backup-id"
        mocks["tracker"].is_file_processed.return_value = False
        mocks["tracker"].log_file_start.return_value = 1

        mocks["reader"].read.side_effect = Exception("corrupt file")

        uc = ConsolidateInvoicesUseCase(**mocks, config=config)
        report = uc.execute()

        assert report.status == "ERROR"
        assert report.files_with_errors == ["test.xlsx"]

    def test_tracker_called_on_start(self, config, mocks):
        mocks["path_resolver"].resolve_path.return_value = "folder-id"
        mocks["drive"].find_file_in_folder.return_value = "consol-id"
        mocks["drive"].list_source_files.return_value = []

        uc = ConsolidateInvoicesUseCase(**mocks, config=config)
        uc.execute()

        mocks["tracker"].start_run.assert_called_once()
        mocks["tracker"].finish_run.assert_called()

    def test_consolidated_not_found_raises_error(self, config, mocks):
        mocks["path_resolver"].resolve_path.return_value = "folder-id"
        mocks["drive"].find_file_in_folder.return_value = None

        uc = ConsolidateInvoicesUseCase(**mocks, config=config)
        report = uc.execute()

        assert report.status == "ERROR"
