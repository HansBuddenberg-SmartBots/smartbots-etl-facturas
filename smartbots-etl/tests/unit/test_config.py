import tempfile
from pathlib import Path

import pytest
import yaml

from src.application.config import load_config, ExcelConfig


def _write_yaml(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "test_config.yaml"
    path.write_text(yaml.dump(data, default_flow_style=False), encoding="utf-8")
    return path


def _minimal_config() -> dict:
    return {
        "google": {"credentials_path": "/tmp/creds.json"},
        "drive": {"source_path": "Bot RPA/Tocornal/ETL Facturas"},
        "email": {"sender": "etl@test.com", "to": ["dest@test.com"]},
    }


class TestLoadConfig:
    def test_loads_valid_yaml(self, tmp_path):
        config = load_config(_write_yaml(tmp_path, _minimal_config()))
        assert config.google.credentials_path == "/tmp/creds.json"
        assert config.drive.source_path == "Bot RPA/Tocornal/ETL Facturas"
        assert config.email.sender == "etl@test.com"

    def test_defaults_applied(self, tmp_path):
        config = load_config(_write_yaml(tmp_path, _minimal_config()))
        assert config.drive.in_process_folder == "En Proceso"
        assert config.drive.backup_path == "Respaldo"
        assert config.drive.consolidated_path == "Consolidado"
        assert config.tracking.db_path == "data/etl_tracking.db"
        assert config.logging.level == "INFO"

    def test_missing_google_section_raises(self, tmp_path):
        data = _minimal_config()
        del data["google"]
        with pytest.raises(ValueError, match="google"):
            load_config(_write_yaml(tmp_path, data))

    def test_missing_drive_section_raises(self, tmp_path):
        data = _minimal_config()
        del data["drive"]
        with pytest.raises(ValueError, match="drive"):
            load_config(_write_yaml(tmp_path, data))

    def test_missing_email_section_raises(self, tmp_path):
        data = _minimal_config()
        del data["email"]
        with pytest.raises(ValueError, match="email"):
            load_config(_write_yaml(tmp_path, data))

    def test_missing_credentials_path_raises(self, tmp_path):
        data = _minimal_config()
        del data["google"]["credentials_path"]
        with pytest.raises(ValueError, match="credentials_path"):
            load_config(_write_yaml(tmp_path, data))

    def test_missing_source_path_raises(self, tmp_path):
        data = _minimal_config()
        del data["drive"]["source_path"]
        with pytest.raises(ValueError, match="source_path"):
            load_config(_write_yaml(tmp_path, data))

    def test_missing_email_sender_raises(self, tmp_path):
        data = _minimal_config()
        del data["email"]["sender"]
        with pytest.raises(ValueError, match="sender"):
            load_config(_write_yaml(tmp_path, data))

    def test_file_not_found_raises(self):
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/config.yaml")

    def test_invalid_yaml_content(self, tmp_path):
        path = tmp_path / "bad.yaml"
        path.write_text("just a string", encoding="utf-8")
        with pytest.raises(ValueError, match="dict"):
            load_config(path)

    def test_email_lists_become_tuples(self, tmp_path):
        data = _minimal_config()
        data["email"]["cc"] = ["cc@test.com"]
        data["email"]["bcc"] = ["bcc@test.com"]
        config = load_config(_write_yaml(tmp_path, data))
        assert isinstance(config.email.to, tuple)
        assert isinstance(config.email.cc, tuple)
        assert isinstance(config.email.bcc, tuple)

    def test_expected_columns_become_tuple(self, tmp_path):
        data = _minimal_config()
        data["excel"] = {"expected_columns": ["Col A", "Col B"]}
        config = load_config(_write_yaml(tmp_path, data))
        assert isinstance(config.excel.expected_columns, tuple)
        assert config.excel.expected_columns == ("Col A", "Col B")

    def test_templates_dict_preserved(self, tmp_path):
        data = _minimal_config()
        data["email"]["templates"] = {
            "success": "Exito.html",
            "error": "Error.html",
        }
        config = load_config(_write_yaml(tmp_path, data))
        assert config.email.templates["success"] == "Exito.html"


class TestExcelConfigDefaults:
    def test_default_expected_columns(self):
        config = ExcelConfig()
        assert len(config.expected_columns) == 9
        assert "N° Factura" in config.expected_columns

    def test_default_column_mapping(self):
        config = ExcelConfig()
        assert config.column_mapping["N° Factura"] == "invoice_number"
        assert config.column_mapping["Monto Total"] == "total_amount"
