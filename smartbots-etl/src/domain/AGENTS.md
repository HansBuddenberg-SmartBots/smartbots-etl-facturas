# Domain Layer (DDD)

Entidades, valor_objects y excepciones de dominio. Cero dependencias externas.

## Estructura

```
domain/
├── __init__.py
├── entities.py       # InvoiceRecord (entidad principal), RecordStatus (enum)
├── exceptions.py     # ConsolidationError, SchemaValidationError, ReconciliationError
└── value_objects.py  # Money (valor para cálculos financieros)
```

## Donde buscar

| Tarea | Ubicación |
|-------|-----------|
| Definir entidades (InvoiceRecord) | entities.py |
| Añadir validaciones de dominio | __post_init__ en entidades |
| Crear excepciones personalizadas | exceptions.py |
| Definir valor objects (Money) | value_objects.py |

## Patrones

- **Inmutabilidad**: Todas las entidades usan `@dataclass(frozen=True, kw_only=True)`
- **Validación cruzada**: __post_init__ valida invariants de negocio
- **Valor objects**: Money para cálculos financieros precisos con Decimal

## Anti-Patrones (NO hacer)

| Patrón | Problema |
|--------|----------|
| `float` para montos | Pérdida precisión - usar `Decimal` |
| `Optional[X]` | Python 3.10+ usar `X \| None` |
| Lógica de negocio en entidades | Solo validación, lógica en application/use_cases |

## Ejemplos

```python
# Entidad inmutable
@dataclass(frozen=True, kw_only=True)
class InvoiceRecord:
    invoice_number: str
    total_amount: Decimal

    def __post_init__(self) -> None:
        if self.total_amount < 0:
            raise ValueError("total_amount no puede ser negativo")

# Valor object
@dataclass(frozen=True)
class Money:
    amount: Decimal
    currency: str = "CLP"
```
