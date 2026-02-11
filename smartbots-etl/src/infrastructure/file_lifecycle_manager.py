"""Gestiona el ciclo de vida de archivos: source → En Proceso → Respaldo/yyyy-mm-dd/hh.mi.ss."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog

from src.application.config import DrivePathsConfig
from src.infrastructure.drive_path_resolver import DrivePathResolver

logger = structlog.get_logger()


class FileLifecycleManager:
    """Mueve archivos a través de sus etapas de ciclo de vida en Google Drive."""

    def __init__(
        self,
        drive_service: Any,
        path_resolver: DrivePathResolver,
        config: DrivePathsConfig,
        shared_drive_id: str | None = None,
    ) -> None:
        self._service = drive_service
        self._path_resolver = path_resolver
        self._config = config
        self._shared_drive_id = shared_drive_id
        self._in_process_folder_id: str | None = None

    def move_to_in_process(self, file_id: str, source_folder_id: str) -> str:
        """Mueve archivo de source → source/En Proceso/. Retorna file_id."""
        in_process_path = f"{self._config.source_path}/{self._config.in_process_folder}"
        in_process_id = self._path_resolver.ensure_path(in_process_path)

        self._move_file(file_id, source_folder_id, in_process_id)
        self._in_process_folder_id = in_process_id

        logger.info(
            "file_moved_to_in_process",
            file_id=file_id,
            folder_id=in_process_id,
        )
        return file_id

    def move_to_backup(self, file_id: str, in_process_folder_id: str | None = None) -> str:
        """Mueve archivo de En Proceso → Respaldo/yyyy-mm-dd/hh.mi.ss/. Retorna file_id."""
        from_folder = in_process_folder_id or self._in_process_folder_id
        if not from_folder:
            msg = "No se puede mover a backup: folder de origen desconocido"
            raise ValueError(msg)

        backup_folder_id = self._ensure_backup_folders()
        self._move_file(file_id, from_folder, backup_folder_id)

        logger.info(
            "file_moved_to_backup",
            file_id=file_id,
            backup_folder_id=backup_folder_id,
        )
        return file_id

    def _ensure_backup_folders(self) -> str:
        """Crea la jerarquía Respaldo/yyyy-mm-dd/hh.mi.ss. Retorna folder ID del timestamp."""
        now = datetime.now(UTC)
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H.%M.%S")

        backup_full = f"{self._config.source_path}/{self._config.backup_path}/{date_str}/{time_str}"
        return self._path_resolver.ensure_path(backup_full)

    def _move_file(self, file_id: str, from_folder_id: str, to_folder_id: str) -> None:
        """Mueve un archivo entre carpetas usando Drive API."""
        params: dict[str, Any] = {
            "fileId": file_id,
            "body": {},
            "addParents": to_folder_id,
            "removeParents": from_folder_id,
        }
        if self._shared_drive_id:
            params["supportsAllDrives"] = True

        self._service.files().update(**params).execute()
