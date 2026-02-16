"""Gestiona el ciclo de vida de archivos: source → En Proceso → Respaldo/yyyy-mm-dd/hh.mi.ss."""

from __future__ import annotations

from datetime import datetime
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
        self._backup_folder_id: str | None = None
        self._backup_date_str: str | None = None
        self._backup_time_str: str | None = None

    def init_backup_folder(self) -> str:
        """
        Inicializa el folder de backup con la fecha/hora actual.
        Debe llamarse al inicio de la ejecución.
        Retorna el ID del folder de backup.
        """
        now = datetime.now()
        self._backup_date_str = now.strftime("%Y-%m-%d")
        self._backup_time_str = now.strftime("%H.%M.%S")

        backup_full = f"{self._config.source_path}/{self._config.backup_path}/{self._backup_date_str}/{self._backup_time_str}"
        self._backup_folder_id = self._path_resolver.ensure_path(backup_full)

        logger.debug(
            "backup_folder_initialized",
            backup_path=backup_full,
            backup_folder_id=self._backup_folder_id,
        )

        return self._backup_folder_id

    def move_to_in_process(self, file_id: str, source_folder_id: str) -> str:
        """
        Mueve archivo de source → source/En Proceso/.
        También crea una copia en Respaldo/fecha/hora/.
        Retorna file_id.
        """
        in_process_path = f"{self._config.source_path}/{self._config.in_process_folder}"
        in_process_id = self._path_resolver.ensure_path(in_process_path)

        # Primero crear backup antes de mover
        self._copy_to_backup(file_id)

        # Luego mover a En Proceso
        self._move_file(file_id, source_folder_id, in_process_id)
        self._in_process_folder_id = in_process_id

        logger.info(
            "file_moved_to_in_process",
            file_id=file_id,
            folder_id=in_process_id,
        )
        return file_id

    def _copy_to_backup(self, file_id: str) -> None:
        """
        Crea una copia del archivo en la carpeta de backup.
        """
        if self._backup_folder_id is None:
            self.init_backup_folder()

        # Obtener el nombre del archivo
        file_metadata = self._service.files().get(fileId=file_id, fields="name").execute()
        file_name = file_metadata.get("name", "unknown")

        # Copiar el archivo al folder de backup
        body = {"name": file_name, "parents": [self._backup_folder_id]}
        params = {"fileId": file_id, "body": body}
        if self._shared_drive_id:
            params["supportsAllDrives"] = True

        self._service.files().copy(**params).execute()

        logger.info(
            "file_copied_to_backup",
            file_id=file_id,
            file_name=file_name,
            backup_folder_id=self._backup_folder_id,
        )

    def move_to_backup(self, file_id: str, in_process_folder_id: str | None = None) -> str:
        """Mueve archivo de En Proceso → Respaldo/yyyy-mm-dd/hh.mi.ss/. Retorna file_id."""
        from_folder = in_process_folder_id or self._in_process_folder_id
        if not from_folder:
            msg = "No se puede mover a backup: folder de origen desconocido"
            raise ValueError(msg)

        # Usar el folder de backup ya inicializado (o inicializar si no existe)
        if self._backup_folder_id is None:
            self.init_backup_folder()

        self._move_file(file_id, from_folder, self._backup_folder_id)

        logger.info(
            "file_moved_to_backup",
            file_id=file_id,
            backup_folder_id=self._backup_folder_id,
        )
        return file_id

    def backup_consolidated(self, consolidated_file_id: str, run_id: str) -> str:
        """
        Crea backup del archivo consolidado en la carpeta Respaldo/yyyy-mm-dd/hh.mi.ss/.
        Usa la fecha/hora inicializada con init_backup_folder().
        Retorna el ID del folder de backup.
        """
        # Usar el folder de backup ya inicializado
        if self._backup_folder_id is None:
            # Si no se ha inicializado, hacerlo ahora
            self.init_backup_folder()

        # Nombre del archivo de backup
        backup_name = f"consolidado_backup_prerun_{run_id[:8]}.xlsx"

        # DEBUG: Mostrar ruta completa del backup
        logger.debug(
            "debug_backup_path",
            backup_path=f"{self._config.source_path}/{self._config.backup_path}/{self._backup_date_str}/{self._backup_time_str}/{backup_name}",
            backup_name=backup_name,
        )

        # Copiar el archivo consolidado al folder de backup
        body = {"name": backup_name, "parents": [self._backup_folder_id]}
        params = {
            "fileId": consolidated_file_id,
            "body": body,
        }
        if self._shared_drive_id:
            params["supportsAllDrives"] = True

        result = self._service.files().copy(**params).execute()
        backup_file_id = result["id"]

        logger.info(
            "consolidated_backup_created",
            original_file_id=consolidated_file_id,
            backup_file_id=backup_file_id,
            backup_folder_id=self._backup_folder_id,
            backup_name=backup_name,
        )

        return self._backup_folder_id

    def _ensure_backup_folders(self) -> str:
        """Crea la jerarquía Respaldo/yyyy-mm-dd/hh.mi.ss. Retorna folder ID del timestamp."""
        # Usar hora local del sistema
        now = datetime.now()
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
