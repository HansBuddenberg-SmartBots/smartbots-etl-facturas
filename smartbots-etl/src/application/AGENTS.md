# Application Layer

Casos de uso, puertos (contracts), DTOs y transformadores de datos.

## Estructura

```
application/
├── __init__.py
├── config.py          # AppConfig (YAML), generación de configs
├── dtos.py            # ExecutionReport, UpsertResult
├── transformers.py    # RowTransformer (convierte filas a entidades)
├── ports/             # Interfaces Contract
│   ├── excel_handler.py
│   ├── drive_repository.py
│   ├── notifier.py
│   └── tracker.py
└── use_cases/         # Orquestación de negocio
    └── consolidate_invoices.py
```

## Donde buscar

| Tarea | Ubicación |
|-------|-----------|
| Caso de uso principal (consolidar facturas) | use_cases/consolidate_invoices.py |
| Puertos/interfaces (contracts) | ports/ |
| Configuración de la app | config.py |
| Transformadores de datos | transformers.py |
| DTOs (reportes, resultados) | dtos.py |

## Patrones

- **Dependency Injection**: Usa puertos Protocol para inyección de dependencias
- **Frozen Dataclasses**: Config y DTOs son inmutables
- **Orquestación simple**: Use cases organizan flujo sin lógica de dominio

## Anti-Patrones (NO hacer)

| Patrón | Problema |
|--------|----------|
| Lógica de negocio en use case | Solo orquestación, lógica en domain |
| `except Exception` | Capturar excepciones específicas |
| Modificar estado en use case | Inmutabilidad, retornar DTOs |

## Ejemplos

```python
# Use case con inyección de dependencias
@dataclass(frozen=True)
class ConsolidateInvoicesUseCase:
    drive: DriveRepository
    reader: ExcelReader
    writer: ExcelWriter

    def execute(self) -> ExecutionReport:
        # Orchestra el proceso de consolidación
```

```python
# Puerto Contract usando Protocol
class DriveRepository(Protocol):
    def list_source_files(self, folder_id: str) -> list[dict]: ...
    def download_file(self, file_id: str, local_path: Path) -> Path: ...
```
application/
├── __init__.py
├── config.py          # AppConfig (YAML), generación de configs
├── dtos.py            # ExecutionReport, UpsertResult
├── transformers.py    # RowTransformer (convierte filas a entidades)
├── ports/             # Interfaces Contract
│   ├── excel_handler.py
│   ├── drive_repository.py
│   ├── notifier.py
│   └── tracker.py
└── use_cases/         # Orquestación de negocio
    └── consolidate_invoices.py
```

## Donde buscar

| Tarea | Ubicación |
|-------|-----------|
| Caso de uso principal (consolidar facturas) | use_cases/consolidate_invoices.py |
| Puertos/interfaces (contracts) | ports/ |
| Configuración de la app | config.py |
| Transformadores de datos | transformers.py |
| DTOs (reportes, resultados) | dtos.py |

## Patrones

- **Dependency Injection**: Usa puertos Protocol para inyección de dependencias
- **Frozen Dataclasses**: Config y DTOs son inmutables
- **Orquestación simple**: Use cases organizan flujo sin lógica de dominio

## Ejemplos

```python
# Use case con inyección de dependencias
@dataclass(frozen=True)
class ConsolidateInvoicesUseCase:
    drive: DriveRepository
    reader: ExcelReader
    writer: ExcelWriter

    def execute(self) -> ExecutionReport:
        # Orquesta el proceso de consolidación
```

```python
# Puerto Contract usando Protocol
class DriveRepository(Protocol):
    def list_source_files(self, folder_id: str) -> list[dict]: ...
    def download_file(self, file_id: str, local_path: Path) -> Path: ...
```
