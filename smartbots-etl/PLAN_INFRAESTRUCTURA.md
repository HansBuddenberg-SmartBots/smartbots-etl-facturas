# Plan Detallado: Rediseño Infraestructura ETL Facturas

> Versión: 1.0 | Fecha: 2026-02-11
> Proyecto: smartbots-etl
> Root: `/Volumes/Resources/Developments/Projects/SmartBots/Santa_Elena/Operaciones_ETL-Facturas/smartbots-etl/`

---

## 0. Resumen Ejecutivo

Se rediseña la capa de infraestructura del ETL de consolidación de facturas para:
- Reemplazar IDs de Drive por **resolución de rutas legibles** (`"Bot RPA/Tocornal/ETL Facturas"`)
- Implementar **ciclo de vida de archivos** en Drive (origen → En Proceso → Respaldo)
- Migrar de `.env` a **configuración YAML**
- Reemplazar SMTP por **Gmail API** con soporte to/cc/bcc y templates HTML
- Reemplazar `processed_manifest.json` por **SQLite** con trazabilidad a 2 niveles (archivo + registro)

**Capas que NO se tocan:** Dominio (`entities.py`, `value_objects.py`, `exceptions.py`), lógica de upsert, reconciliación, parseo de montos/fechas. Solo se modifican infraestructura, configuración, ports y orquestación.

---

## 1. Componentes a Crear/Modificar

### 1.1 Archivos NUEVOS (9 archivos)

| # | Archivo | Responsabilidad |
|---|---------|-----------------|
| 1 | `configs/configuration.yaml` | Configuración central: rutas Drive, credenciales, email, columnas, SQLite |
| 2 | `src/infrastructure/drive_path_resolver.py` | Resuelve rutas legibles a folder IDs. Detecta Shared Drive vs My Drive |
| 3 | `src/infrastructure/file_lifecycle_manager.py` | Mueve archivos: origen → En Proceso → Respaldo/yyyy-mm-dd/hh.mi.ss |
| 4 | `src/infrastructure/gmail_notifier.py` | Envío de emails via Gmail API con to/cc/bcc y templates HTML |
| 5 | `src/infrastructure/sqlite_tracker.py` | Tracking SQLite: execution_runs, file_log, record_log |
| 6 | `src/templates/ETL_Consolidacion_Exito.html` | Template: ejecución exitosa |
| 7 | `src/templates/ETL_Consolidacion_Parcial.html` | Template: éxito parcial (algunos registros fallaron) |
| 8 | `src/templates/ETL_Consolidacion_Error.html` | Template: error fatal |
| 9 | `src/templates/ETL_Consolidacion_Vacio.html` | Template: sin archivos para procesar |

### 1.2 Archivos MODIFICADOS (7 archivos)

| # | Archivo | Cambio |
|---|---------|--------|
| 1 | `src/application/ports/drive_repository.py` | Agregar: `resolve_path()`, `move_file()`, `create_folder()`, `ensure_folder_path()` |
| 2 | `src/application/ports/notifier.py` | Agregar: campos `cc`, `bcc`, `html_body`, `template_name` |
| 3 | `src/application/dtos.py` | Reemplazar `ConsolidationConfig` por `YamlConfig` cargado desde YAML. Agregar DTOs para SQLite |
| 4 | `src/application/use_cases/consolidate_invoices.py` | Integrar: SQLite tracker, file lifecycle, path resolution |
| 5 | `src/infrastructure/google_drive_adapter.py` | Agregar: path resolver, file move, folder creation, Shared Drive detection |
| 6 | `scripts/run_consolidation.py` | Cargar YAML en vez de .env. Instanciar nuevos componentes |
| 7 | `pyproject.toml` | Agregar deps: `pyyaml`, quitar `pydantic` (innecesario), agregar scope gmail |

### 1.3 Archivos ELIMINADOS/DEPRECADOS (3 archivos)

| # | Archivo | Razón |
|---|---------|-------|
| 1 | `.env.example` | Reemplazado por `configs/configuration.yaml` |
| 2 | `src/infrastructure/smtp_notifier.py` | Reemplazado por `gmail_notifier.py` |
| 3 | `data/processed_manifest.json` | Reemplazado por SQLite |

---

## 2. Diseño Detallado por Componente

### 2.1 Configuración YAML

**Archivo:** `configs/configuration.yaml`

```yaml
# === Google APIs ===
google:
  credentials_path: "./credentials/service_account.json"
  # Si se trabaja en Shared Drive, indicar el nombre. Vacío = My Drive.
  shared_drive_name: ""
  # Email del usuario a impersonar para Gmail API (domain-wide delegation)
  delegated_user: "bot-rpa@santaelena.cl"

# === Rutas en Google Drive ===
drive:
  source_path: "Bot RPA/Tocornal/ETL Facturas"
  in_process_folder: "En Proceso"          # Subcarpeta dentro de source_path
  backup_path: "Respaldo"                  # Subcarpeta dentro de source_path
  consolidated_path: "Consolidado"         # Ruta desde raíz de Drive
  consolidated_filename: "consolidado.xlsx"

# === Excel ===
excel:
  source_sheet: "Sheet1"
  consolidated_sheet: "Consolidado"
  expected_columns:
    - "N° Factura"
    - "N° Referencia"
    - "Transportista"
    - "Fecha Factura"
    - "Descripción"
    - "Monto Neto"
    - "IVA"
    - "Monto Total"
    - "Moneda"
  column_mapping:
    "N° Factura": "invoice_number"
    "N° Referencia": "reference_number"
    "Transportista": "carrier_name"
    "Fecha Factura": "invoice_date"
    "Descripción": "description"
    "Monto Neto": "net_amount"
    "IVA": "tax_amount"
    "Monto Total": "total_amount"
    "Moneda": "currency"
  date_format: "%d-%m-%Y"

# === Email (Gmail API) ===
email:
  sender: "bot-rpa@santaelena.cl"
  to:
    - "operaciones@santaelena.cl"
  cc:
    - "supervisor@santaelena.cl"
  bcc:
    - "auditoria@santaelena.cl"
  subject_prefix: "[Smartbots ETL]"
  templates:
    success: "ETL_Consolidacion_Exito.html"
    partial: "ETL_Consolidacion_Parcial.html"
    error: "ETL_Consolidacion_Error.html"
    empty: "ETL_Consolidacion_Vacio.html"

# === Tracking (SQLite) ===
tracking:
  db_path: "data/etl_tracking.db"

# === Logging ===
logging:
  level: "INFO"
  log_to_file: true
  log_dir: "logs"
```

**Carga:** Se lee con `PyYAML` y se mapea a un `@dataclass` tipado:

```python
@dataclass(frozen=True)
class GoogleConfig:
    credentials_path: str
    shared_drive_name: str
    delegated_user: str

@dataclass(frozen=True)
class DrivePathsConfig:
    source_path: str
    in_process_folder: str
    backup_path: str
    consolidated_path: str
    consolidated_filename: str

@dataclass(frozen=True)
class EmailConfig:
    sender: str
    to: list[str]
    cc: list[str]
    bcc: list[str]
    subject_prefix: str
    templates: dict[str, str]

@dataclass(frozen=True)
class AppConfig:
    google: GoogleConfig
    drive: DrivePathsConfig
    excel: ExcelConfig
    email: EmailConfig
    tracking: TrackingConfig
    logging: LoggingConfig
```

---

### 2.2 Drive Path Resolver

**Archivo:** `src/infrastructure/drive_path_resolver.py`

**Responsabilidad:** Convertir rutas legibles como `"Bot RPA/Tocornal/ETL Facturas"` en folder IDs de Google Drive.

**Algoritmo:**
```
1. Detectar si es Shared Drive o My Drive
   - Si config.shared_drive_name está definido → buscar Shared Drive por nombre → usar como raíz
   - Si no → usar 'root' como raíz (My Drive)
2. Split path por "/" → segmentos = ["Bot RPA", "Tocornal", "ETL Facturas"]
3. Para cada segmento:
   a. Query: name='segmento' AND 'parent_id' in parents AND mimeType=folder AND trashed=false
   b. Si no encuentra → error DrivePathNotFoundError
   c. Si encuentra multiple → usar el primero (log warning)
   d. current_id = resultado.id
4. Retornar current_id final
5. Cachear resultados en dict {path_string: folder_id} durante la ejecución
```

**API call exacto:**
```python
query = (
    f"name='{segment}' "
    f"and '{parent_id}' in parents "
    f"and mimeType='application/vnd.google-apps.folder' "
    f"and trashed=false"
)

params = {"q": query, "fields": "files(id, name)", "pageSize": 10}

# Si es Shared Drive, agregar:
if shared_drive_id:
    params["driveId"] = shared_drive_id
    params["corpora"] = "drive"
    params["includeItemsFromAllDrives"] = True
    params["supportsAllDrives"] = True

results = service.files().list(**params).execute()
```

**Método público:**
```python
def resolve_path(self, path: str) -> str:
    """Retorna folder_id. Raises DrivePathNotFoundError si no existe."""

def ensure_path(self, path: str) -> str:
    """Resuelve path, creando carpetas que no existan. Retorna folder_id."""
```

---

### 2.3 File Lifecycle Manager

**Archivo:** `src/infrastructure/file_lifecycle_manager.py`

**Responsabilidad:** Gestionar el movimiento de archivos XLSX a través de su ciclo de vida en Drive.

**Flujo de un archivo:**
```
source_path/archivo.xlsx
    │
    ▼ (1) move_to_in_process()
source_path/En Proceso/archivo.xlsx
    │
    ▼ (2) proceso ETL...
    │
    ▼ (3) move_to_backup()
source_path/Respaldo/2026-02-11/14.30.45/archivo.xlsx
```

**Operaciones:**

```python
class FileLifecycleManager:
    def __init__(self, drive_service, path_resolver, config):
        ...

    def move_to_in_process(self, file_id: str, source_folder_id: str) -> str:
        """
        Mueve archivo de source → source/En Proceso/.
        Crea la carpeta "En Proceso" si no existe.
        Retorna el file_id (no cambia).
        
        API: files().update(fileId=X, addParents=en_proceso_id, removeParents=source_id)
        """

    def move_to_backup(self, file_id: str, in_process_folder_id: str) -> str:
        """
        Mueve archivo de En Proceso → Respaldo/yyyy-mm-dd/hh.mi.ss/.
        Crea la estructura Respaldo/fecha/hora si no existe.
        Retorna el file_id.
        
        Ruta backup: {source_path}/Respaldo/{date}/{time}/
        Formato date: 2026-02-11
        Formato time: 14.30.45
        """

    def _ensure_backup_folders(self, base_folder_id: str) -> str:
        """
        Crea la jerarquía Respaldo/yyyy-mm-dd/hh.mi.ss si no existe.
        Retorna el folder_id de la carpeta de timestamp.
        """
```

**API call para mover:**
```python
service.files().update(
    fileId=file_id,
    body={},
    addParents=target_folder_id,
    removeParents=source_folder_id,
    supportsAllDrives=True
).execute()
```

**API call para crear carpeta:**
```python
metadata = {
    "name": folder_name,
    "mimeType": "application/vnd.google-apps.folder",
    "parents": [parent_id]
}
folder = service.files().create(
    body=metadata,
    fields="id",
    supportsAllDrives=True
).execute()
```

---

### 2.4 Gmail Notifier

**Archivo:** `src/infrastructure/gmail_notifier.py`

**Reemplaza:** `src/infrastructure/smtp_notifier.py`

**Scopes requeridos:**
```python
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
```

**Autenticación:**
```python
creds = Credentials.from_service_account_file(credentials_path, scopes=GMAIL_SCOPES)
delegated = creds.with_subject(delegated_user)  # Impersona al usuario
service = build("gmail", "v1", credentials=delegated)
```

**Interfaz:**
```python
class GmailNotifier:
    def __init__(self, credentials_path: str, delegated_user: str, templates_dir: Path):
        ...

    def send(
        self,
        subject: str,
        template_name: str,
        template_vars: dict,
        recipients: list[str],
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        attachments: list[Path] | None = None,
    ) -> str:
        """
        1. Carga template HTML desde templates_dir/template_name
        2. Interpola template_vars con str.format()
        3. Construye MIMEMultipart con To/Cc/Bcc
        4. Adjunta archivos si los hay
        5. Encode base64url
        6. Envía via users().messages().send(userId='me', body={'raw': encoded})
        7. Retorna message_id
        """
```

**Construcción del mensaje MIME:**
```python
msg = MIMEMultipart("mixed")
msg["From"] = sender
msg["To"] = ", ".join(recipients)
msg["Subject"] = subject
if cc:
    msg["Cc"] = ", ".join(cc)
if bcc:
    msg["Bcc"] = ", ".join(bcc)

# HTML body
alternative = MIMEMultipart("alternative")
alternative.attach(MIMEText(text_fallback, "plain"))
alternative.attach(MIMEText(html_body, "html"))
msg.attach(alternative)

# Attachments...

raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
service.users().messages().send(userId="me", body={"raw": raw}).execute()
```

---

### 2.5 SQLite Tracker

**Archivo:** `src/infrastructure/sqlite_tracker.py`

**Reemplaza:** `data/processed_manifest.json`

**Schema (3 tablas):**

```sql
-- Tabla 1: Ejecuciones
CREATE TABLE IF NOT EXISTS execution_runs (
    run_uuid     TEXT PRIMARY KEY,
    started_at   TEXT NOT NULL,      -- ISO 8601
    finished_at  TEXT,               -- ISO 8601, NULL si aún corriendo
    status       TEXT NOT NULL,      -- RUNNING | SUCCESS | PARTIAL | ERROR | NO_FILES
    total_files  INTEGER DEFAULT 0,
    total_records INTEGER DEFAULT 0,
    inserted     INTEGER DEFAULT 0,
    updated      INTEGER DEFAULT 0,
    unchanged    INTEGER DEFAULT 0,
    errors       INTEGER DEFAULT 0,
    source_total_amount TEXT,        -- Decimal como string
    output_total_amount TEXT,        -- Decimal como string
    message      TEXT
);

-- Tabla 2: Log a nivel de archivo
CREATE TABLE IF NOT EXISTS file_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_uuid        TEXT NOT NULL REFERENCES execution_runs(run_uuid),
    file_name       TEXT NOT NULL,
    file_drive_id   TEXT,
    file_modified_time TEXT,
    schema_valid    INTEGER,         -- 1=valid, 0=invalid
    missing_columns TEXT,            -- JSON array
    extra_columns   TEXT,            -- JSON array
    rows_total      INTEGER DEFAULT 0,
    rows_valid      INTEGER DEFAULT 0,
    rows_error      INTEGER DEFAULT 0,
    status          TEXT NOT NULL,    -- PROCESSING | COMPLETED | SKIPPED | ERROR
    error_message   TEXT,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Tabla 3: Log a nivel de registro
CREATE TABLE IF NOT EXISTS record_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_uuid        TEXT NOT NULL REFERENCES execution_runs(run_uuid),
    file_log_id     INTEGER NOT NULL REFERENCES file_log(id),
    row_index       INTEGER NOT NULL,
    invoice_number  TEXT,
    reference_number TEXT,
    action          TEXT NOT NULL,    -- INSERT | UPDATE | UNCHANGED | VALIDATION_ERROR | TRANSFORM_ERROR
    error_message   TEXT,             -- NULL si éxito
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_file_log_run ON file_log(run_uuid);
CREATE INDEX IF NOT EXISTS idx_record_log_run ON record_log(run_uuid);
CREATE INDEX IF NOT EXISTS idx_record_log_file ON record_log(file_log_id);
CREATE INDEX IF NOT EXISTS idx_record_log_action ON record_log(action);
```

**Interfaz:**
```python
class SqliteTracker:
    def __init__(self, db_path: str):
        """Inicializa conexión y crea tablas si no existen."""

    def start_run(self, run_uuid: str) -> None:
        """INSERT INTO execution_runs con status=RUNNING."""

    def finish_run(self, run_uuid: str, status: str, counters: dict) -> None:
        """UPDATE execution_runs SET finished_at, status, contadores."""

    def log_file_start(self, run_uuid: str, file_name: str, file_drive_id: str) -> int:
        """INSERT INTO file_log. Retorna file_log.id."""

    def log_file_schema(self, file_log_id: int, valid: bool, missing: list, extra: list) -> None:
        """UPDATE file_log SET schema_valid, missing_columns, extra_columns."""

    def log_file_finish(self, file_log_id: int, status: str, rows_total: int,
                        rows_valid: int, rows_error: int, error_message: str | None) -> None:
        """UPDATE file_log SET status, finished_at, contadores."""

    def log_record(self, run_uuid: str, file_log_id: int, row_index: int,
                   invoice_number: str | None, reference_number: str | None,
                   action: str, error_message: str | None) -> None:
        """INSERT INTO record_log."""

    def log_records_batch(self, records: list[dict]) -> None:
        """INSERT batch para performance."""

    def is_file_processed(self, file_name: str, modified_time: str) -> bool:
        """
        Reemplaza el check de idempotencia del manifest JSON.
        SELECT 1 FROM file_log WHERE file_name=? AND file_modified_time=? AND status='COMPLETED'
        """

    def get_run_summary(self, run_uuid: str) -> dict:
        """Retorna resumen de la ejecución para el reporte."""
```

---

### 2.6 HTML Email Templates

**Estructura visual (heredada de templates existentes):**
- Header: Logo Santa Elena (`https://smart-bots.cl/logo_santahelena.jpg`)
- Body: Contenido con placeholders `{variable}`
- Footer: `© 2025 Exportadora Santa Elena S.A.`

**Template 1: `ETL_Consolidacion_Exito.html`**
Placeholders:
- `{run_id}` — ID de ejecución
- `{timestamp}` — Fecha/hora
- `{archivos_procesados}` — Lista `<li>` de archivos
- `{registros_insertados}` — Conteo
- `{registros_actualizados}` — Conteo
- `{registros_sin_cambios}` — Conteo
- `{total_monto_origen}` — Monto total origen formateado
- `{total_monto_destino}` — Monto total destino formateado
- `{varianza}` — Varianza monetaria

**Template 2: `ETL_Consolidacion_Parcial.html`**
Igual que Exito + tabla de errores:
- `{errores_validacion}` — Filas `<tr>` con errores por registro

**Template 3: `ETL_Consolidacion_Error.html`**
- `{run_id}`, `{timestamp}`
- `{error_tipo}` — Tipo de error (SCHEMA_ERROR, RECONCILIATION_FAILED, etc.)
- `{error_detalle}` — Mensaje de error
- `{rollback_ejecutado}` — Sí/No

**Template 4: `ETL_Consolidacion_Vacio.html`**
- `{run_id}`, `{timestamp}`
- Mensaje estático: no se encontraron archivos para procesar

---

### 2.7 Modificaciones al Port DriveRepository

**Archivo:** `src/application/ports/drive_repository.py`

Métodos nuevos:
```python
class DriveRepository(Protocol):
    # ... métodos existentes ...

    def resolve_path(self, path: str) -> str:
        """Resuelve ruta legible a folder_id."""
        ...

    def move_file(self, file_id: str, from_folder_id: str, to_folder_id: str) -> None:
        """Mueve archivo entre carpetas."""
        ...

    def create_folder(self, name: str, parent_id: str) -> str:
        """Crea carpeta. Retorna folder_id."""
        ...

    def find_file_in_folder(self, folder_id: str, file_name: str) -> str | None:
        """Busca archivo por nombre en carpeta. Retorna file_id o None."""
        ...
```

### 2.8 Modificaciones al Port Notifier

**Archivo:** `src/application/ports/notifier.py`

```python
class Notifier(Protocol):
    def send(
        self,
        subject: str,
        template_name: str,
        template_vars: dict,
        recipients: list[str],
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        attachments: list[Path] | None = None,
    ) -> None: ...
```

---

## 3. Flujo de Ejecución Rediseñado

```
1. INICIO
   └─ Cargar configuration.yaml → AppConfig
   └─ Inicializar: DriveAdapter, PathResolver, LifecycleManager, ExcelHandler, GmailNotifier, SqliteTracker
   └─ SqliteTracker.start_run(run_uuid)

2. RESOLVER RUTAS
   └─ PathResolver.resolve_path("Bot RPA/Tocornal/ETL Facturas") → source_folder_id
   └─ PathResolver.resolve_path("Consolidado") → consolidated_folder_id
   └─ DriveAdapter.find_file_in_folder(consolidated_folder_id, "consolidado.xlsx") → consolidated_file_id

3. LISTAR ARCHIVOS ORIGEN
   └─ DriveAdapter.list_source_files(source_folder_id) → files[]
   └─ Si vacío → status=NO_FILES, enviar template Vacio, FIN

4. POR CADA ARCHIVO:
   a. CHECK IDEMPOTENCIA
      └─ SqliteTracker.is_file_processed(name, modified_time)
      └─ Si ya procesado → skip, log SKIPPED
   
   b. MOVER A "EN PROCESO"
      └─ LifecycleManager.move_to_in_process(file_id, source_folder_id)
      └─ SqliteTracker.log_file_start(run_uuid, file_name, file_id)
   
   c. DESCARGAR Y VALIDAR
      └─ DriveAdapter.download_file(file_id, /tmp/)
      └─ ExcelReader.read() → df
      └─ ExcelReader.validate_schema() → valid/missing/extra
      └─ SqliteTracker.log_file_schema(file_log_id, valid, missing, extra)
      └─ Si inválido → error, mover a backup, continuar siguiente archivo
   
   d. TRANSFORMAR Y VALIDAR FILAS
      └─ Por cada fila: RowTransformer.transform_row()
      └─ Por cada resultado: SqliteTracker.log_record(action=INSERT|UPDATE|ERROR, ...)
   
   e. DESCARGAR CONSOLIDADO + BACKUP
      └─ DriveAdapter.download_file(consolidated_file_id, /tmp/)
      └─ DriveAdapter.create_backup(consolidated_file_id, backup_name)
   
   f. UPSERT + RECONCILIAR
      └─ _upsert(existing, incoming) → UpsertResult
      └─ _reconcile(source_records, upsert_result)
      └─ Si falla → rollback, mover a backup, log error
   
   g. SUBIR CONSOLIDADO
      └─ ExcelWriter.write(df_result, /tmp/consolidado.xlsx)
      └─ DriveAdapter.update_file(consolidated_file_id, /tmp/consolidado.xlsx)
   
   h. MOVER A RESPALDO
      └─ LifecycleManager.move_to_backup(file_id, in_process_folder_id)
      └─ SqliteTracker.log_file_finish(file_log_id, COMPLETED, ...)

5. FINALIZAR
   └─ SqliteTracker.finish_run(run_uuid, status, counters)
   └─ Seleccionar template según status (Exito/Parcial/Error/Vacio)
   └─ GmailNotifier.send(subject, template, vars, to, cc, bcc)
   └─ FIN
```

---

## 4. Plan de Ejecución (Fases Ordenadas)

### Fase 1: Configuración YAML + Carga
**Prioridad:** Alta (todo depende de esto)
**Archivos:**
- CREAR `configs/configuration.yaml`
- CREAR `src/application/config.py` (dataclasses de config + función `load_config`)
- MODIFICAR `pyproject.toml` (agregar `pyyaml`)
- ELIMINAR `.env.example`

**Criterio de éxito:** `load_config("configs/configuration.yaml")` retorna `AppConfig` tipado.

---

### Fase 2: Drive Path Resolver
**Prioridad:** Alta (el lifecycle manager depende de esto)
**Archivos:**
- CREAR `src/infrastructure/drive_path_resolver.py`
- MODIFICAR `src/application/ports/drive_repository.py` (agregar métodos)
- MODIFICAR `src/infrastructure/google_drive_adapter.py` (implementar métodos nuevos)

**Criterio de éxito:** `resolve_path("Bot RPA/Tocornal/ETL Facturas")` retorna folder_id. Detect Shared/My Drive.

---

### Fase 3: File Lifecycle Manager
**Prioridad:** Alta
**Archivos:**
- CREAR `src/infrastructure/file_lifecycle_manager.py`
- MODIFICAR `src/infrastructure/google_drive_adapter.py` (agregar `move_file`, `create_folder`)

**Criterio de éxito:** Archivo se mueve a "En Proceso", luego a "Respaldo/2026-02-11/14.30.45/".

---

### Fase 4: SQLite Tracker
**Prioridad:** Alta (el use case necesita esto para logging)
**Archivos:**
- CREAR `src/infrastructure/sqlite_tracker.py`
- CREAR `src/application/ports/tracker.py` (Protocol para el tracker)
- ELIMINAR `data/processed_manifest.json`

**Criterio de éxito:** `start_run`, `log_file_*`, `log_record`, `finish_run` funcionan. `is_file_processed` reemplaza check de idempotencia.

---

### Fase 5: Gmail Notifier + Templates HTML
**Prioridad:** Media (puede funcionar sin email temporalmente)
**Archivos:**
- CREAR `src/infrastructure/gmail_notifier.py`
- CREAR 4 templates HTML en `src/templates/`
- MODIFICAR `src/application/ports/notifier.py` (nueva interfaz)
- ELIMINAR `src/infrastructure/smtp_notifier.py`

**Criterio de éxito:** Email HTML enviado via Gmail API con to/cc/bcc y template interpolado.

---

### Fase 6: Integración — Use Case + Orchestrator
**Prioridad:** Alta (después de fases 1-5)
**Archivos:**
- MODIFICAR `src/application/use_cases/consolidate_invoices.py` (integrar todos los componentes nuevos)
- MODIFICAR `scripts/run_consolidation.py` (cargar YAML, instanciar componentes nuevos)
- MODIFICAR `src/application/dtos.py` (limpiar DTOs obsoletos)

**Criterio de éxito:** Ejecución completa end-to-end con YAML config, path resolution, lifecycle, SQLite tracking, Gmail notification.

---

### Fase 7: Tests
**Prioridad:** Media (después de implementación)
**Archivos:**
- CREAR `tests/unit/test_config.py`
- CREAR `tests/unit/test_path_resolver.py`
- CREAR `tests/unit/test_sqlite_tracker.py`
- CREAR `tests/unit/test_gmail_notifier.py`
- MODIFICAR `tests/unit/test_use_case.py` (actualizar mocks)

**Criterio de éxito:** Todos los tests pasan.

---

## 5. Dependencias entre Fases

```
Fase 1 (YAML Config)
  ├──▶ Fase 2 (Path Resolver) ──▶ Fase 3 (Lifecycle Manager)
  ├──▶ Fase 4 (SQLite Tracker)
  └──▶ Fase 5 (Gmail + Templates)
                                    │
                                    ▼
                           Fase 6 (Integración)
                                    │
                                    ▼
                           Fase 7 (Tests)
```

Fases 2-5 pueden ejecutarse en paralelo después de Fase 1.
Fase 6 requiere que todas las anteriores estén completas.
Fase 7 va al final.

---

## 6. Dependencias de Paquetes (cambios a pyproject.toml)

```toml
# AGREGAR:
"pyyaml>=6.0",

# MANTENER:
"pandas>=2.2",
"openpyxl>=3.1",
"google-api-python-client>=2.160",
"google-auth>=2.37",
"structlog>=24.4",
"python-dotenv>=1.0",      # Puede eliminarse si todo va a YAML

# NO SE NECESITA (stdlib):
# sqlite3 — incluido en Python
```

---

## 7. Riesgos y Mitigaciones

| Riesgo | Impacto | Mitigación |
|--------|---------|------------|
| Shared Drive tiene permisos distintos a My Drive | Alto | Detectar automáticamente y usar `supportsAllDrives=True` en todas las llamadas |
| Carpetas duplicadas con el mismo nombre en Drive | Medio | Tomar la primera, loggear warning. No es un error fatal |
| Gmail domain-wide delegation no configurada | Alto | Validar al inicio: intentar enviar test email, fallar rápido con mensaje claro |
| SQLite concurrencia (si se ejecuta en paralelo) | Bajo | Por ahora es single-process. Si escala, migrar a WAL mode |
| Templates con placeholders incorrectos | Bajo | Validar que todos los placeholders del template estén en template_vars |
| Path resolution lenta (muchos API calls) | Bajo | Cache de paths resueltos durante la ejecución |

---

## 8. Archivos Finales (Estado Post-Implementación)

```
smartbots-etl/
├── configs/
│   └── configuration.yaml              ← NUEVO
├── credentials/
│   └── service_account.json            (gitignored)
├── data/
│   └── etl_tracking.db                 ← NUEVO (reemplaza manifest.json)
├── logs/
├── scripts/
│   └── run_consolidation.py            ← MODIFICADO
├── src/
│   ├── __init__.py
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── entities.py                 (sin cambios)
│   │   ├── value_objects.py            (sin cambios)
│   │   └── exceptions.py              (sin cambios)
│   ├── application/
│   │   ├── __init__.py
│   │   ├── config.py                   ← NUEVO
│   │   ├── dtos.py                     ← MODIFICADO
│   │   ├── transformers.py             (sin cambios)
│   │   ├── ports/
│   │   │   ├── __init__.py
│   │   │   ├── drive_repository.py     ← MODIFICADO
│   │   │   ├── excel_handler.py        (sin cambios)
│   │   │   ├── notifier.py             ← MODIFICADO
│   │   │   └── tracker.py             ← NUEVO
│   │   └── use_cases/
│   │       ├── __init__.py
│   │       └── consolidate_invoices.py ← MODIFICADO
│   ├── infrastructure/
│   │   ├── __init__.py
│   │   ├── google_drive_adapter.py     ← MODIFICADO
│   │   ├── drive_path_resolver.py      ← NUEVO
│   │   ├── file_lifecycle_manager.py   ← NUEVO
│   │   ├── excel_handler.py            (sin cambios)
│   │   ├── gmail_notifier.py           ← NUEVO
│   │   ├── sqlite_tracker.py           ← NUEVO
│   │   └── logging_config.py           (sin cambios)
│   └── templates/
│       ├── Envio_Informe.html          (existente, sin cambios)
│       ├── Envio_Informe_v0.html       (existente, sin cambios)
│       ├── Envio_Recibidor.html        (existente, sin cambios)
│       ├── Envio_Vacio.html            (existente, sin cambios)
│       ├── ETL_Consolidacion_Exito.html    ← NUEVO
│       ├── ETL_Consolidacion_Parcial.html  ← NUEVO
│       ├── ETL_Consolidacion_Error.html    ← NUEVO
│       └── ETL_Consolidacion_Vacio.html    ← NUEVO
├── tests/
│   ├── unit/
│   │   ├── test_entities.py            (sin cambios)
│   │   ├── test_transformers.py        (sin cambios)
│   │   ├── test_use_case.py            ← MODIFICADO
│   │   ├── test_config.py             ← NUEVO
│   │   ├── test_path_resolver.py      ← NUEVO
│   │   ├── test_sqlite_tracker.py     ← NUEVO
│   │   └── test_gmail_notifier.py     ← NUEVO
│   └── integration/
├── pyproject.toml                      ← MODIFICADO
├── Dockerfile                          (sin cambios)
└── .gitignore                          ← MODIFICADO (agregar *.db)
```

**Conteo: 9 archivos nuevos, 7 modificados, 3 eliminados.**
