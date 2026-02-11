from unittest.mock import MagicMock, call

import pytest

from src.infrastructure.drive_path_resolver import DrivePathResolver, DrivePathNotFoundError


def _mock_service(folder_results: dict[str, list[dict]] | None = None):
    service = MagicMock()

    def files_list(**kwargs):
        mock_resp = MagicMock()
        q = kwargs.get("q", "")
        if folder_results:
            for name, files in folder_results.items():
                if f"name='{name}'" in q:
                    mock_resp.execute.return_value = {"files": files}
                    return mock_resp
        mock_resp.execute.return_value = {"files": []}
        return mock_resp

    service.files().list.side_effect = files_list
    return service


class TestResolvePath:
    def test_single_segment(self):
        service = _mock_service({"Consolidado": [{"id": "folder-c", "name": "Consolidado"}]})
        resolver = DrivePathResolver(service)
        result = resolver.resolve_path("Consolidado")
        assert result == "folder-c"

    def test_multi_segment_path(self):
        service = _mock_service(
            {
                "Bot RPA": [{"id": "id-1", "name": "Bot RPA"}],
                "Tocornal": [{"id": "id-2", "name": "Tocornal"}],
                "ETL Facturas": [{"id": "id-3", "name": "ETL Facturas"}],
            }
        )
        resolver = DrivePathResolver(service)
        result = resolver.resolve_path("Bot RPA/Tocornal/ETL Facturas")
        assert result == "id-3"

    def test_cache_hit(self):
        service = _mock_service({"Consolidado": [{"id": "folder-c", "name": "Consolidado"}]})
        resolver = DrivePathResolver(service)
        resolver.resolve_path("Consolidado")
        resolver.resolve_path("Consolidado")
        assert service.files().list.call_count == 1

    def test_not_found_raises(self):
        service = _mock_service()
        resolver = DrivePathResolver(service)
        with pytest.raises(DrivePathNotFoundError, match="NoExiste"):
            resolver.resolve_path("NoExiste")

    def test_shared_drive_params(self):
        service = _mock_service({"Test": [{"id": "t1", "name": "Test"}]})
        resolver = DrivePathResolver(service, shared_drive_id="sd-123")
        resolver.resolve_path("Test")
        call_kwargs = service.files().list.call_args[1]
        assert call_kwargs.get("supportsAllDrives") is True
        assert call_kwargs.get("driveId") == "sd-123"
        assert call_kwargs.get("corpora") == "drive"


class TestEnsurePath:
    def test_creates_missing_folder(self):
        service = MagicMock()
        call_count = {"n": 0}

        def files_list(**kwargs):
            mock_resp = MagicMock()
            call_count["n"] += 1
            if call_count["n"] == 1:
                mock_resp.execute.return_value = {"files": []}
            else:
                mock_resp.execute.return_value = {"files": [{"id": "existing", "name": "x"}]}
            return mock_resp

        service.files().list.side_effect = files_list
        service.files().create.return_value.execute.return_value = {"id": "new-folder"}

        resolver = DrivePathResolver(service)
        result = resolver.ensure_path("NewFolder")
        assert result == "new-folder"
        service.files().create.assert_called_once()


class TestDetectSharedDrive:
    def test_returns_drive_id(self):
        service = MagicMock()
        service.drives().list.return_value.execute.return_value = {
            "drives": [{"id": "sd-1", "name": "Mi Drive Compartido"}]
        }
        result = DrivePathResolver.detect_shared_drive(service, "Mi Drive Compartido")
        assert result == "sd-1"

    def test_returns_none_when_not_found(self):
        service = MagicMock()
        service.drives().list.return_value.execute.return_value = {"drives": []}
        result = DrivePathResolver.detect_shared_drive(service, "NoExiste")
        assert result is None

    def test_returns_none_for_empty_name(self):
        service = MagicMock()
        result = DrivePathResolver.detect_shared_drive(service, "")
        assert result is None
