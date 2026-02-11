# Draft: Rediseño Infraestructura ETL Facturas

## Requirements (confirmed)
- **Drive Path Resolution**: User provides paths like `"Bot RPA/Tocornal/ETL Facturas"`, system resolves to folder IDs walking the path from root. No hardcoded IDs.
- **File Lifecycle**: Find XLSX → Move to `"En Proceso"` subfolder → Process → Move to `"Respaldo/yyyy-mm-dd/hh.mi.ss"` subfolder
- **Consolidado Location**: At root-level path `"Consolidado"` in Drive
- **Config Format**: YAML file (not .env) for all non-secret config. Must include credentials folder path.
- **Email via Gmail API**: Replace SMTP with Gmail API (service account). Must support: to, cc, bcc fields.
- **HTML Email Templates**: New template inspired by existing ones (same CSS structure: Santa Elena logo header, table layout, footer). But content specific to ETL consolidation results.
- **SQLite Tracking DB**: Replace `processed_manifest.json` with SQLite database. Two log levels:
  1. **File-level log**: file name, validations of original file, timestamp, processing result
  2. **Record-level log**: per-row status, error field for failed records
  3. **Common UUID**: Both levels linked by a shared execution UUID

## Technical Decisions
- **Path resolution**: Walk segments via Drive API `files().list()` with `name=X and 'parentId' in parents and mimeType=folder`
- **File move**: Use `files().update()` with `addParents`/`removeParents`
- **Gmail API**: `users().messages().send()` with base64-encoded MIME, scopes `gmail.send`
- **Template system**: Python `string.Template` or `.format()` with placeholders (matching existing pattern)
- **SQLite**: stdlib `sqlite3`, no ORM needed. Tables: `execution_log`, `file_log`, `record_log`

## Research Findings
- **Templates analyzed** (4 existing):
  - `Envio_Informe.html` — Success template with `{asuntos_exitosos}` list items
  - `Envio_Informe_v0.html` — Success template with `{Ordenes_Embarque}` list items
  - `Envio_Recibidor.html` — Generic body template with `{cuerpo}` placeholder
  - `Envio_Vacio.html` — Static "no records found" message
  - All share: Santa Elena logo, table-based email layout, copyright footer
  - All use Python `.format()` style placeholders `{variable_name}`

## Open Questions
1. **Shared Drive or My Drive?** — Path resolution differs. Shared Drives use `driveId` + `corpora=drive`. My Drive uses `'root' in parents`.
2. **Service account email delegation** — Which Gmail address should send emails? (needs domain-wide delegation to impersonate a user)
3. **"En Proceso" folder** — Does it already exist in Drive, or should the system create it if missing?
4. **"Respaldo" folder** — Same question: auto-create the dated subfolders?
5. **Consolidado file** — Does the XLSX file already exist, or should the system create it on first run?
6. **YAML secrets** — Should secrets (API keys, etc.) still come from .env, or is everything in YAML?
7. **Template scenarios for ETL** — Need at least: success, partial (some rows failed), error, no-files. How many different emails?
8. **SQLite location** — Where should the .db file live? `data/etl_tracking.db`?
9. **Test strategy** — TDD, tests after, or no tests for these infrastructure changes?

## Scope Boundaries
- INCLUDE: Drive path resolver, file lifecycle, YAML config, Gmail API notifier, HTML templates, SQLite tracker
- EXCLUDE: Changes to domain entities, upsert logic, reconciliation logic, Excel handler
