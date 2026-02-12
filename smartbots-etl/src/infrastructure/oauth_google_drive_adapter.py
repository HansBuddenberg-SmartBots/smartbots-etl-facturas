"""OAuth-based Google Drive adapter with token refresh support."""

from pathlib import Path
from typing import Any

import json
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
import structlog

logger = structlog.get_logger()

SCOPES = ["https://www.googleapis.com/auth/drive"]
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class OAuthGoogleDriveAdapter:
    """Google Drive adapter using OAuth2 credentials with token refresh."""

    def __init__(
        self,
        credentials_path: str,
        token_path: str,
        shared_drive_id: str | None = None,
    ) -> None:
        """Initialize adapter with OAuth credentials from credentials.json and token.json.

        Args:
            credentials_path: Path to OAuth client credentials (client_id, client_secret)
            token_path: Path to stored token with refresh_token
            shared_drive_id: Optional Shared Drive ID
        """
        creds_path = Path(credentials_path)
        token_file = Path(token_path)

        # Load OAuth client credentials
        with open(creds_path) as f:
            client_config = json.load(f).get("installed", {})

        # Load stored token
        with open(token_file) as f:
            token_data = json.load(f)

        # Create credentials with refresh capability
        self._creds = Credentials(
            token=token_data.get("token"),
            refresh_token=token_data.get("refresh_token"),
            token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=token_data.get("client_id", client_config.get("client_id")),
            client_secret=token_data.get("client_secret", client_config.get("client_secret")),
            scopes=token_data.get("scopes", SCOPES),
        )

        self._token_path = token_file
        self.service = build("drive", "v3", credentials=self._creds)
        self._shared_drive_id = shared_drive_id

    def _save_token(self) -> None:
        """Save updated token after refresh."""
        token_data = {
            "token": self._creds.token,
            "refresh_token": self._creds.refresh_token,
            "token_uri": self._creds.token_uri,
            "client_id": self._creds.client_id,
            "client_secret": self._creds.client_secret,
            "scopes": self._creds.scopes,
        }
        self._token_path.write_text(json.dumps(token_data, indent=2))

    def _ensure_valid_token(self) -> None:
        """Refresh token if expired."""
        if self._creds.expired:
            self._creds.refresh(None)  # Uses built-in refresh
            self._save_token()
            logger.info("oauth_token_refreshed")

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
        self._ensure_valid_token()
        return self.list_xlsx_in_folder(folder_id)

    def list_xlsx_in_folder(self, folder_id: str) -> list[dict]:
        self._ensure_valid_token()
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
        self._ensure_valid_token()
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
        self._ensure_valid_token()
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
        self._ensure_valid_token()
        metadata: dict[str, Any] = {"name": file_name, "parents": [folder_id]}
        media = MediaFileUpload(str(local_path), mimetype=XLSX_MIME)
        params = self._drive_params(body=metadata, media_body=media, fields="id")
        file = self.service.files().create(**params).execute()
        file_id = file["id"]
        logger.info("drive_file_uploaded", file_id=file_id, name=file_name)
        return file_id

    def create_backup(self, file_id: str, backup_name: str) -> str:
        self._ensure_valid_token()
        body: dict[str, Any] = {"name": backup_name}
        params = self._drive_params(fileId=file_id, body=body)
        backup = self.service.files().copy(**params).execute()
        backup_id = backup["id"]
        logger.info("drive_backup_created", original=file_id, backup=backup_id)
        return backup_id

    def restore_backup(self, backup_file_id: str, original_file_id: str) -> None:
        self._ensure_valid_token()
        backup_path = Path(f"/tmp/restore_{backup_file_id}.xlsx")
        self.download_file(backup_file_id, backup_path)
        self.update_file(original_file_id, backup_path)
        logger.warning("drive_backup_restored", backup=backup_file_id, original=original_file_id)

    def update_file(self, file_id: str, local_path: Path) -> None:
        self._ensure_valid_token()
        media = MediaFileUpload(str(local_path), mimetype=XLSX_MIME)
        params = self._drive_params(fileId=file_id, media_body=media)
        self.service.files().update(**params).execute()
        logger.info("drive_file_updated", file_id=file_id)

    def move_file(self, file_id: str, from_folder_id: str, to_folder_id: str) -> None:
        self._ensure_valid_token()
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
