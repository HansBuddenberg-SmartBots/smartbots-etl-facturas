# SmartBots ETL

ETL de consolidación de facturas XLSX vía Google Drive con arquitectura hexagonal (DDD).

## Estructura

```
smartbots-etl/
├── src/                     # Capa de dominio, aplicación e infraestructura
│   ├── domain/             # Entidades, valor_objects, excepciones
│   ├── application/        # Casos de uso, puertos, DTOs, transformadores
│   └── infrastructure/     # Implementaciones de servicios externos
├── tests/                   # Tests unitarios e integración
├── scripts/                 # Scripts de entrada (run_consolidation.py, etc)
├── configs/                # configuration.yaml
├── data/                   # SQLite tracking database
├── logs/                   # Logs de aplicación
└── templates/              # Plantillas de email (HTML)
```

## Comandos

```bash
# Development
uv pip install -e ".[dev]"

# Tests
pytest

# Linting
ruff check
ruff format

# Type checking
mypy

# Docker
docker build -t smartbots-etl .
docker run --rm -v $(pwd)/configs:/app/configs smartbots-etl
```

## Dependencies

- Python >= 3.12
- pandas >= 3.0
- openpyxl >= 3.1.5
- google-api-python-client >= 2.189.0
- google-auth >= 2.48.0
- structlog >= 25.5.0
- pyyaml >= 6.0.3
- pydantic >= 2.12.5
