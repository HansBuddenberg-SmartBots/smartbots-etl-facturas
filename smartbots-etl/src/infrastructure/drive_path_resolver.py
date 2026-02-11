"""Resuelve rutas legibles de Google Drive a folder IDs."""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger()

FOLDER_MIME = "application/vnd.google-apps.folder"


class DrivePathNotFoundError(Exception):
    """Un segmento de ruta no fue encontrado en Google Drive."""

    def __init__(self, segment: str, parent_id: str) -> None:
        self.segment = segment
        self.parent_id = parent_id
        super().__init__(f"Carpeta '{segment}' no encontrada en Drive (parent_id={parent_id})")


class DrivePathResolver:
    """Convierte rutas como 'Bot RPA/Tocornal/ETL Facturas' a folder IDs de Drive."""

    def __init__(self, drive_service: Any, shared_drive_id: str | None = None) -> None:
        self._service = drive_service
        self._shared_drive_id = shared_drive_id
        self._cache: dict[str, str] = {}

    @classmethod
    def detect_shared_drive(cls, drive_service: Any, shared_drive_name: str) -> str | None:
        """Busca un Shared Drive por nombre. Retorna drive_id o None."""
        if not shared_drive_name:
            return None

        results = (
            drive_service.drives()
            .list(q=f"name='{shared_drive_name}'", fields="drives(id, name)")
            .execute()
        )
        drives = results.get("drives", [])
        if not drives:
            logger.warning("shared_drive_not_found", name=shared_drive_name)
            return None

        drive_id: str = drives[0]["id"]
        logger.info("shared_drive_detected", name=shared_drive_name, drive_id=drive_id)
        return drive_id

    def resolve_path(self, path: str) -> str:
        """Resuelve una ruta separada por '/' a un folder ID.

        Raises DrivePathNotFoundError si algún segmento no existe.
        """
        if path in self._cache:
            return self._cache[path]

        segments = [s.strip() for s in path.split("/") if s.strip()]
        current_id = self._shared_drive_id or "root"

        for i, segment in enumerate(segments):
            partial = "/".join(segments[: i + 1])
            if partial in self._cache:
                current_id = self._cache[partial]
                continue

            current_id = self._find_folder(segment, current_id)
            self._cache[partial] = current_id

        self._cache[path] = current_id
        return current_id

    def ensure_path(self, path: str) -> str:
        """Resuelve ruta, creando carpetas que no existan. Retorna folder ID final."""
        segments = [s.strip() for s in path.split("/") if s.strip()]
        current_id = self._shared_drive_id or "root"

        for i, segment in enumerate(segments):
            partial = "/".join(segments[: i + 1])
            if partial in self._cache:
                current_id = self._cache[partial]
                continue

            try:
                current_id = self._find_folder(segment, current_id)
            except DrivePathNotFoundError:
                current_id = self._create_folder(segment, current_id)

            self._cache[partial] = current_id

        self._cache[path] = current_id
        return current_id

    def _find_folder(self, name: str, parent_id: str) -> str:
        """Busca una carpeta por nombre dentro de un padre. Raises DrivePathNotFoundError."""
        query = (
            f"name='{name}' "
            f"and '{parent_id}' in parents "
            f"and mimeType='{FOLDER_MIME}' "
            f"and trashed=false"
        )
        params: dict[str, Any] = {
            "q": query,
            "fields": "files(id, name)",
            "pageSize": 10,
        }
        if self._shared_drive_id:
            params["driveId"] = self._shared_drive_id
            params["corpora"] = "drive"
            params["includeItemsFromAllDrives"] = True
            params["supportsAllDrives"] = True

        results = self._service.files().list(**params).execute()
        files = results.get("files", [])

        if not files:
            raise DrivePathNotFoundError(name, parent_id)

        if len(files) > 1:
            logger.warning(
                "drive_duplicate_folders",
                name=name,
                parent_id=parent_id,
                count=len(files),
            )

        folder_id: str = files[0]["id"]
        return folder_id

    def _create_folder(self, name: str, parent_id: str) -> str:
        """Crea una carpeta en Drive. Retorna el nuevo folder ID."""
        metadata: dict[str, Any] = {
            "name": name,
            "mimeType": FOLDER_MIME,
            "parents": [parent_id],
        }
        params: dict[str, Any] = {"body": metadata, "fields": "id"}
        if self._shared_drive_id:
            params["supportsAllDrives"] = True

        folder = self._service.files().create(**params).execute()
        folder_id: str = folder["id"]
        logger.info("drive_folder_created", name=name, folder_id=folder_id)
        return folder_id
