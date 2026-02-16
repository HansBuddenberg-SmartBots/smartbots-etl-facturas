# SmartBots ETL

ETL de consolidación de facturas XLSX vía Google Drive con arquitectura hexagonal (DDD).

## Estructura

```
smartbots-etl/
├── src/
│   ├── domain/              # Entidades, value objects, excepciones (0 deps externas)
│   ├── application/         # Casos de uso, puertos, DTOs, transformadores
│   └── infrastructure/     # Implementaciones: Drive, Gmail, Excel, SQLite
├── tests/
│   ├── unit/               # Tests con mocks
│   └── integration/        # Tests con infra real, fakes para APIs
├── scripts/                # Entry points (run_consolidation.py, etc)
├── configs/                # configuration.yaml
├── data/                   # SQLite tracking
├── logs/                   # structlog JSON
└── templates/              # Plantillas HTML email
```

## Entry Points

| Script | Propósito |
|--------|-----------|
| `scripts/run_consolidation.py` | **Principal**: ETL completo Drive → Excel → consolidación → email |
| `scripts/authenticate.py` | OAuth2 para Google APIs |
| `scripts/test_oauth.py` | Valida conexiones OAuth |
| `scripts/check_drive_structure.py` | Debug: inspecciona estructura Drive |

## Comandos

```bash
# Development
uv pip install -e ".[dev]"

# Tests
pytest                    # Todos
pytest tests/unit/        # Solo unitarios
pytest tests/integration/ # Solo integración (requiere --marker integration)

# Linting
ruff check
ruff check --fix         # Auto-corregir

# Formateo
ruff format

# Type checking
mypy
mypy --strict src/

# Docker
docker build -t smartbots-etl .
docker run --rm -v $(pwd)/configs:/app/configs smartbots-etl
```

## Dependencias

- Python >= 3.12
- pandas >= 3.0, openpyxl >= 3.1.5
- google-api-python-client >= 2.189.0, google-auth >= 2.48.0
- structlog >= 25.5.0, pyyaml >= 6.0.3, pydantic >= 2.12.5

---

## Anti-Patrones (ESTE PROYECTO)

### NO hacer:

| Patrón | Problema | Alternativa |
|--------|----------|-------------|
| `as any`, `@ts-ignore` | Suprime type errors | Tipos correctos |
| `except Exception` | Captura too broad | Excepciones específicas |
| `float` para dinero | Errores precisión | `Decimal` |
| `Optional[str]` | Python 3.10- | `str \| None` |
| Imports relativos | `from ..domain` | `from src.domain` |

### Known Issues:

- **Config file**: Usar `configs/configuration.yaml` (NO `consolidation.yaml`)
- **sys.path manipulation**: Scripts usan workaround para imports - instalar con `uv pip install -e .`
- **Entry points**: No hay `[project.scripts]` en pyproject.toml - ejecutar como `python scripts/xxx.py`

---

## Patrones No Estándar

| Área | Actual | Estándar |
|------|--------|----------|
| CLI entry points | `python scripts/run_consolidation.py` | `smartbots-consolidate` command |
| sys.path | Workaround manual | Package installation |
| CI/CD | Manual | GitHub Actions |
| Pre-commit | No existe | .pre-commit-config.yaml |

---

## Testing

- **Fixtures**: `tests/conftest.py` + `tests/integration/conftest.py`
- **XLSX factories**: `create_source_xlsx()`, `create_consolidated_xlsx()`
- **Fake boundary**: Drive/Gmail (fake), SQLite/Excel (real)
- **Marker**: `@pytest.mark.integration` para tests con I/O real
