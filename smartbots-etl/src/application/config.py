"""Configuración de la aplicación cargada desde YAML."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class GoogleConfig:
    credentials_path: str
    token_path: str = "./credentials/token.json"


@dataclass(frozen=True)
class DrivePathsConfig:
    source_path: str
    in_process_folder: str = "En Proceso"
    backup_path: str = "Respaldo"
    consolidated_path: str = "Consolidado"
    consolidated_filename: str = "consolidado.xlsx"


@dataclass(frozen=True)
class ExcelConfig:
    source_sheet: str = "Sheet1"
    consolidated_sheet: str = "Consolidado"
    header_row: int = 11
    data_start_row: int = 12
    skip_schema_validation: bool = False
    expected_columns: tuple[str, ...] = (
        "N° Factura",
        "N° Referencia",
        "Transportista",
        "Fecha Factura",
        "Descripción",
        "Monto Neto",
        "IVA",
        "Monto Total",
        "Moneda",
    )
    column_mapping: dict[str, str] = field(
        default_factory=lambda: {
            "N° Factura": "invoice_number",
            "N° Referencia": "reference_number",
            "Transportista": "carrier_name",
            "Fecha Factura": "invoice_date",
            "Descripción": "description",
            "Monto Neto": "net_amount",
            "IVA": "tax_amount",
            "Monto Total": "total_amount",
            "Moneda": "currency",
        }
    )
    date_format: str = "%d-%m-%Y"


@dataclass(frozen=True)
class EmailConfig:
    sender: str
    to: tuple[str, ...] = ()
    cc: tuple[str, ...] = ()
    bcc: tuple[str, ...] = ()
    subject_prefix: str = "[Smartbots ETL]"
    templates: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class TrackingConfig:
    db_path: str = "data/etl_tracking.db"


@dataclass(frozen=True)
class LoggingConfig:
    level: str = "INFO"
    log_to_file: bool = True
    log_dir: str = "logs"


@dataclass(frozen=True)
class AppConfig:
    google: GoogleConfig
    drive: DrivePathsConfig
    excel: ExcelConfig
    email: EmailConfig
    tracking: TrackingConfig
    logging: LoggingConfig


def load_config(config_path: str | Path) -> AppConfig:
    """Carga y valida la configuración desde un archivo YAML."""
    # Resuelve la ruta de forma absoluta para evitar problemas con el directorio de trabajo actual
    path = Path(config_path).resolve()
    if not path.exists():
        msg = f"Archivo de configuración no encontrado: {path}"
        raise FileNotFoundError(msg)

    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        msg = f"YAML inválido: se esperaba dict, se obtuvo {type(raw).__name__}"
        raise ValueError(msg)

    _validate_required_keys(raw)

    return AppConfig(
        google=_build_google_config(raw.get("google", {})),
        drive=_build_drive_config(raw.get("drive", {})),
        excel=_build_excel_config(raw.get("excel", {})),
        email=_build_email_config(raw.get("email", {})),
        tracking=TrackingConfig(**raw.get("tracking", {})),
        logging=LoggingConfig(**raw.get("logging", {})),
    )


def _validate_required_keys(raw: dict[str, Any]) -> None:
    """Valida que las secciones requeridas existan en el YAML."""
    required = {"google", "drive", "email"}
    missing = required - set(raw.keys())
    if missing:
        msg = f"Secciones requeridas faltantes en YAML: {sorted(missing)}"
        raise ValueError(msg)


def _build_google_config(data: dict[str, Any]) -> GoogleConfig:
    if "credentials_path" not in data:
        msg = "google.credentials_path es requerido"
        raise ValueError(msg)
    return GoogleConfig(**data)


def _build_drive_config(data: dict[str, Any]) -> DrivePathsConfig:
    if "source_path" not in data:
        msg = "drive.source_path es requerido"
        raise ValueError(msg)
    return DrivePathsConfig(**data)


def _build_excel_config(data: dict[str, Any]) -> ExcelConfig:
    """Construye ExcelConfig, convirtiendo listas a tuplas para frozen dataclass."""
    data = dict(data)  # shallow copy
    if "expected_columns" in data:
        data["expected_columns"] = tuple(data["expected_columns"])
    return ExcelConfig(**data)


def _build_email_config(data: dict[str, Any]) -> EmailConfig:
    """Construye EmailConfig, convirtiendo listas a tuplas para frozen dataclass."""
    data = dict(data)  # shallow copy
    if "sender" not in data:
        msg = "email.sender es requerido"
        raise ValueError(msg)
    for key in ("to", "cc", "bcc"):
        if key in data:
            data[key] = tuple(data[key])
    return EmailConfig(**data)
