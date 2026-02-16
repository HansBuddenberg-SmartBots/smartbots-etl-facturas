# SmartBots ETL - Invoice Consolidation

[![Release](https://img.shields.io/github/v/release/HansBuddenberg-SmartBots/smartbots-etl-facturas)](https://github.com/HansBuddenberg-SmartBots/smartbots-etl-facturas/releases)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

ETL system for invoice consolidation via Google Drive with hexagonal architecture (DDD).

---

## 🇬🇧 English

### Overview

Automated ETL pipeline that:
- Extracts invoice data from Excel files in Google Drive
- Consolidates records into a master file
- Sends email notifications with results
- Tracks all executions in SQLite

### Features

| Feature | Description |
|---------|-------------|
| **Extraction** | Reads Excel files with specific column mapping |
| **Consolidation** | Inserts only new records (no updates/deletes) |
| **Formatting** | Preserves column formats (numbers, dates, alignment) |
| **Notifications** | Email alerts for SUCCESS, PARTIAL, ERROR, NO_FILES |
| **Tracking** | SQLite database for execution history |
| **Backup** | Automatic file backup with timestamp folders |

### Quick Start

```bash
# Clone repository
git clone https://github.com/HansBuddenberg-SmartBots/smartbots-etl-facturas.git
cd smartbots-etl-facturas/smartbots-etl

# Install dependencies
uv pip install -e ".[dev]"

# Setup credentials
cp configs/configuration.yaml.template configs/configuration.yaml
# Edit configuration.yaml with your values

# Place Google OAuth credentials
mkdir -p credentials
# Add credentials.json and token.json

# Run consolidation
python scripts/run_consolidation.py
```

### Project Structure

```
smartbots-etl/
├── src/
│   ├── domain/              # Entities, value objects, exceptions
│   ├── application/         # Use cases, ports, DTOs, transformers
│   └── infrastructure/      # Drive, Gmail, Excel, SQLite implementations
├── tests/
│   ├── unit/               # Tests with mocks
│   └── integration/         # Tests with real infrastructure
├── scripts/                 # Entry points
├── configs/                 # Configuration files
├── templates/               # Email HTML templates
└── data/                    # SQLite tracking database
```

### Configuration

| Section | Description |
|---------|-------------|
| `google` | OAuth credentials paths |
| `drive` | Google Drive folder paths |
| `excel` | Column mapping, sheet names |
| `email` | Recipients, templates |
| `tracking` | SQLite database path |
| `logging` | Log level and file path |

### Email Subjects

| Status | Subject |
|--------|---------|
| SUCCESS | `Consolidacion Facturas - EXITOSO` |
| PARTIAL | `Consolidacion Facturas - ADVERTENCIA` |
| ERROR | `Consolidacion Facturas - ERROR` |
| NO_FILES | `Consolidacion Facturas - SIN ARCHIVOS` |

### Commands

```bash
# Run ETL
python scripts/run_consolidation.py

# Run tests
pytest tests/unit/

# Linting
ruff check

# Type checking
mypy src/
```

---

## 🇪🇸 Español

### Descripción General

Pipeline ETL automatizado que:
- Extrae datos de facturas desde archivos Excel en Google Drive
- Consolida registros en un archivo maestro
- Envía notificaciones por email con los resultados
- Registra todas las ejecuciones en SQLite

### Características

| Característica | Descripción |
|----------------|-------------|
| **Extracción** | Lee archivos Excel con mapeo de columnas específico |
| **Consolidación** | Inserta solo nuevos registros (sin actualizaciones/eliminaciones) |
| **Formato** | Preserva formatos de columnas (números, fechas, alineación) |
| **Notificaciones** | Alertas por email para EXITOSO, ADVERTENCIA, ERROR, SIN ARCHIVOS |
| **Seguimiento** | Base de datos SQLite para historial de ejecuciones |
| **Respaldo** | Backup automático con carpetas por fecha/hora |

### Inicio Rápido

```bash
# Clonar repositorio
git clone https://github.com/HansBuddenberg-SmartBots/smartbots-etl-facturas.git
cd smartbots-etl-facturas/smartbots-etl

# Instalar dependencias
uv pip install -e ".[dev]"

# Configurar credenciales
cp configs/configuration.yaml.template configs/configuration.yaml
# Editar configuration.yaml con sus valores

# Colocar credenciales OAuth de Google
mkdir -p credentials
# Agregar credentials.json y token.json

# Ejecutar consolidación
python scripts/run_consolidation.py
```

### Estructura del Proyecto

```
smartbots-etl/
├── src/
│   ├── domain/              # Entidades, value objects, excepciones
│   ├── application/         # Casos de uso, puertos, DTOs, transformadores
│   └── infrastructure/      # Implementaciones Drive, Gmail, Excel, SQLite
├── tests/
│   ├── unit/               # Tests con mocks
│   └── integration/         # Tests con infraestructura real
├── scripts/                 # Puntos de entrada
├── configs/                 # Archivos de configuración
├── templates/               # Plantillas HTML para emails
└── data/                    # Base de datos SQLite de seguimiento
```

### Configuración

| Sección | Descripción |
|---------|-------------|
| `google` | Rutas de credenciales OAuth |
| `drive` | Rutas de carpetas en Google Drive |
| `excel` | Mapeo de columnas, nombres de hojas |
| `email` | Destinatarios, plantillas |
| `tracking` | Ruta de base de datos SQLite |
| `logging` | Nivel de log y ruta de archivo |

### Asuntos de Email

| Estado | Asunto |
|--------|--------|
| SUCCESS | `Consolidacion Facturas - EXITOSO` |
| PARTIAL | `Consolidacion Facturas - ADVERTENCIA` |
| ERROR | `Consolidacion Facturas - ERROR` |
| NO_FILES | `Consolidacion Facturas - SIN ARCHIVOS` |

### Comandos

```bash
# Ejecutar ETL
python scripts/run_consolidation.py

# Ejecutar tests
pytest tests/unit/

# Linting
ruff check

# Verificación de tipos
mypy src/
```

---

## Security Notes / Notas de Seguridad

- **Never commit credentials** - Use `configuration.yaml.template` and create your own `configuration.yaml`
- **Credentials are in `.gitignore`** - `credentials.json` and `token.json` are excluded
- **Use OAuth2** - Google API authentication via OAuth2 tokens
- **Never commit credentials** - `credentials/` folder is excluded from git

## License / Licencia

MIT License - See [LICENSE](LICENSE) for details.

---

## Releases

| Version | Description |
|---------|-------------|
| [v1.2.0](https://github.com/HansBuddenberg-SmartBots/smartbots-etl-facturas/releases/tag/v1.2.0) | Email subjects in Spanish |
| [v1.1.0](https://github.com/HansBuddenberg-SmartBots/smartbots-etl-facturas/releases/tag/v1.1.0) | Format improvements and config simplification |
| [v1.0.0](https://github.com/HansBuddenberg-SmartBots/smartbots-etl-facturas/releases/tag/v1.0.0) | First stable release |
