from typing import Protocol
from pathlib import Path


class DriveRepository(Protocol):
    def list_source_files(self, folder_id: str) -> list[dict]:
        """Returns: [{"file_id": "...", "name": "...", "modified_time": "..."}]"""
        ...

    def download_file(self, file_id: str, local_path: Path) -> Path: ...

    def upload_file(self, local_path: Path, folder_id: str, file_name: str) -> str: ...

    def create_backup(self, file_id: str, backup_name: str) -> str: ...

    def restore_backup(self, backup_file_id: str, original_file_id: str) -> None: ...

    def update_file(self, file_id: str, local_path: Path) -> None: ...

    def move_file(self, file_id: str, from_folder_id: str, to_folder_id: str) -> None:
        """Mueve un archivo entre carpetas en Drive."""
        ...

    def find_file_in_folder(self, folder_id: str, file_name: str) -> str | None:
        """Busca un archivo por nombre en una carpeta. Retorna file_id o None."""
        ...

    def list_xlsx_in_folder(self, folder_id: str) -> list[dict]:
        """Lista archivos XLSX en una carpeta. Alias de list_source_files."""
        ...
