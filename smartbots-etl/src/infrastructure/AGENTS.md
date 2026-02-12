# Infrastructure Layer

Implementaciones técnicas: Google Drive, Excel, Gmail, SQLite, Notificaciones.

## Estructura

```
infrastructure/
├── __init__.py
├── excel/              # OpenpyxlHandler, FileReader, Writer
│   ├── excel_handler.py
│   ├── file_reader.py
│   └── file_writer.py
├── google_drive/       # OAuthGoogleDriveAdapter
│   ├── google_drive_adapter.py
│   └── oauth.py
├── gmail/              # GmailNotifier
│   ├── gmail_notifier.py
│   └── oauth.py
└── sqlite_tracker.py   # SQLite execution tracker
```

## Donde buscar

| Tarea | Ubicación |
|-------|-----------|
| Procesamiento de Excel | excel/excel_handler.py |
| Conexión Google Drive | google_drive/google_drive_adapter.py |
| Notificaciones Gmail | gmail/gmail_notifier.py |
| Tracking SQLite | sqlite_tracker.py |
| Autenticación OAuth | google_drive/oauth.py / gmail/oauth.py |

## Patrones

- **Adapter Pattern**: Adapters implementan puertos (protocols)
- **Dependency Inversion**: Infra depende de Application ports, no al revés
- **Structured Logging**: structlog con JSON para producción

## Ejemplos

```python
# Adapter que implementa puerto Protocol
class OAuthGoogleDriveAdapter(DriveRepository):
    def __init__(self, credentials_path: Path):
        # Inicializa Google API con OAuth
        pass

    def list_source_files(self, folder_id: str) -> list[dict]:
        # Implementa DriveRepository Protocol
        pass
```
