# Tests Layer

Tests unitarios e integración con fakes realistas para servicios externos.

## Estructura

```
tests/
├── __init__.py
├── conftest.py          # Fixtures compartidos (sys.path manipulación)
├── unit/                # Tests con mocks
│   ├── test_use_case.py
│   ├── test_transformers.py
│   ├── test_sqlite_tracker.py
│   └── test_entities.py
└── integration/         # Tests con infra real, fakes para APIs externas
    ├── conftest.py      # Fixtures ricos con factories
    └── test_consolidation_flow.py
```

## Donde buscar

| Tarea | Ubicación |
|-------|-----------|
| Fixtures de configuración | conftest.py |
| Fixtures con datos XLSX | integration/conftest.py |
| Tests unitarios | unit/ |
| Tests integración (con infra real) | integration/ |
| Fake Drive/Gmail | integration/conftest.py |

## Patrones

- **Fake Boundary**: Fake Drive/Gmail (in-memory), real infra (SQLite, Excel)
- **XLSX Factories**: create_source_xlsx(), create_consolidated_xlsx()
- **sys.path**: manipulación para imports sin instalación del paquete
- **Fixtures enriquecidos**: Real components + fakes para testing
- **Call Tracking**: Fakes capturan llamadas para verificación

## Anti-Patrones (NO hacer)

| Patrón | Problema |
|--------|----------|
| Tests sin marker apropiado | Unit vs integración debe estar marcado |
| Mocks para todo | Usar fakes para APIs externas, real para SQLite/Excel |
| `assert` sin mensaje | pytest assertions deben ser claros |

## Ejemplos

```python
# Fixtures en conftest.py
@pytest.fixture
def tracker(tmp_path):
    return SqliteTracker(tmp_path / "test.db")

@pytest.fixture
def fake_drive():
    return FakeDrive(files={})
```

```python
# XLSX factory para tests
def create_source_xlsx(rows, fixed_cells=None):
    """Crea archivos XLSX de prueba con nombres en español."""
    fixed_cells = fixed_cells or {}
    # ... implementación
```
tests/
├── __init__.py
├── conftest.py          # Fixtures compartidos (sys.path manipulación)
├── unit/                # Tests con mocks
│   ├── test_use_case.py
│   ├── test_transformers.py
│   ├── test_sqlite_tracker.py
│   └── test_entities.py
└── integration/         # Tests con infra real, fakes para APIs externas
    ├── conftest.py      # Fixtures ricos con factories
    ├── test_consolidation_flow.py
    └── test_financial_reconciliation.py
```

## Donde buscar

| Tarea | Ubicación |
|-------|-----------|
| Fixtures de configuración | conftest.py |
| Fixtures con datos XLSX | integration/conftest.py |
| Tests unitarios | unit/ |
| Tests integración (con infra real) | integration/ |
| Fake Drive/Gmail | integration/conftest.py |

## Patrones

- **Fake Boundary**: Fake Drive/Gmail (in-memory), real infra (SQLite, Excel)
- **XLSX Factories**: create_source_xlsx(), create_consolidated_xlsx()
- **sys.path**: manipulación para imports sin instalación del paquete
- **Fixtures enriquecidos**: Real components + fakes para testing

## Ejemplos

```python
# Fixtures en conftest.py
@pytest.fixture
def tracker(tmp_path):
    return SqliteTracker(tmp_path / "test.db")

@pytest.fixture
def fake_drive():
    return FakeDrive(files={})
```

```python
# XLSX factory para tests
def create_source_xlsx(rows, fixed_cells=None):
    """Crea archivos XLSX de prueba con nombres en español."""
    fixed_cells = fixed_cells or {}
    # ... implementación
```
