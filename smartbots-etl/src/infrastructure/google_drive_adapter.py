from pathlib import Path
from typing import Any

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
import structlog

logger = structlog.get_logger()

SCOPES = ["https://www.googleapis.com/auth/drive"]
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class GoogleDriveAdapter:
    def __init__(self, credentials_path: str, shared_drive_id: str | None = None) -> None:
        creds = Credentials.from_service_account_file(credentials_path, scopes=SCOPES)
        self.service = build("drive", "v3", credentials=creds)
        self._shared_drive_id = shared_drive_id

    def _drive_params(self, **extra: Any) -> dict[str, Any]:
        params: dict[str, Any] = dict(extra)
        if self._shared_drive_id:
            params["supportsAllDrives"] = True
            params["includeItemsFromAllDrives"] = True
        return params

    def _list_params(self, **extra: Any) -> dict[str, Any]:
        params = self._drive_params(**extra)
        if self._shared_drive_id:
            params["driveId"] = self._shared_drive_id
            params["corpora"] = "drive"
        return params

    def list_source_files(self, folder_id: str) -> list[dict]:
        return self.list_xlsx_in_folder(folder_id)

    def list_xlsx_in_folder(self, folder_id: str) -> list[dict]:
        query = f"'{folder_id}' in parents and mimeType='{XLSX_MIME}' and trashed=false"
        params = self._list_params(
            q=query,
            fields="files(id, name, modifiedTime)",
            orderBy="modifiedTime desc",
        )
        results = self.service.files().list(**params).execute()

        files = results.get("files", [])
        logger.info("drive_files_listed", folder_id=folder_id, count=len(files))
        return [
            {"file_id": f["id"], "name": f["name"], "modified_time": f["modifiedTime"]}
            for f in files
        ]

    def find_file_in_folder(self, folder_id: str, file_name: str) -> str | None:
        query = f"'{folder_id}' in parents and name='{file_name}' and trashed=false"
        params = self._list_params(
            q=query,
            fields="files(id, name)",
            pageSize=1,
        )
        results = self.service.files().list(**params).execute()
        files = results.get("files", [])
        if not files:
            return None
        file_id: str = files[0]["id"]
        logger.info("drive_file_found", name=file_name, file_id=file_id)
        return file_id

    def download_file(self, file_id: str, local_path: Path) -> Path:
        request = self.service.files().get_media(fileId=file_id, **self._drive_params())
        local_path.parent.mkdir(parents=True, exist_ok=True)
        with open(local_path, "wb") as f:
            downloader = MediaIoBaseDownload(f, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
        logger.info("drive_file_downloaded", file_id=file_id, path=str(local_path))
        return local_path

    def upload_file(self, local_path: Path, folder_id: str, file_name: str) -> str:
        metadata: dict[str, Any] = {"name": file_name, "parents": [folder_id]}
        media = MediaFileUpload(str(local_path), mimetype=XLSX_MIME)
        params = self._drive_params(body=metadata, media_body=media, fields="id")
        file = self.service.files().create(**params).execute()
        file_id = file["id"]
        logger.info("drive_file_uploaded", file_id=file_id, name=file_name)
        return file_id

    def create_backup(self, file_id: str, backup_name: str) -> str:
        body: dict[str, Any] = {"name": backup_name}
        params = self._drive_params(fileId=file_id, body=body)
        backup = self.service.files().copy(**params).execute()
        backup_id = backup["id"]
        logger.info("drive_backup_created", original=file_id, backup=backup_id)
        return backup_id

    def restore_backup(self, backup_file_id: str, original_file_id: str) -> None:
        backup_path = Path(f"/tmp/restore_{backup_file_id}.xlsx")
        self.download_file(backup_file_id, backup_path)
        self.update_file(original_file_id, backup_path)
        logger.warning("drive_backup_restored", backup=backup_file_id, original=original_file_id)

    def update_file(self, file_id: str, local_path: Path) -> None:
        media = MediaFileUpload(str(local_path), mimetype=XLSX_MIME)
        params = self._drive_params(fileId=file_id, media_body=media)
        self.service.files().update(**params).execute()
        logger.info("drive_file_updated", file_id=file_id)

    def move_file(self, file_id: str, from_folder_id: str, to_folder_id: str) -> None:
        params = self._drive_params(
            fileId=file_id,
            body={},
            addParents=to_folder_id,
            removeParents=from_folder_id,
        )
        self.service.files().update(**params).execute()
        logger.info(
            "drive_file_moved",
            file_id=file_id,
            from_folder=from_folder_id,
            to_folder=to_folder_id,
        )
