# Arquitectura Técnica: Ecosistema de Automatización Smartbots

> Documento de bases técnicas para inicio de desarrollo.
> Última actualización: 2026-02-11

---

## 1. Diseño Técnico Detallado

### 1.1 Entidades de Dominio

Todas las entidades usan `@dataclass(frozen=True)` para inmutabilidad. Pydantic se reserva para DTOs y validación de entrada — **no para entidades de dominio**. Razón: las entidades deben ser objetos puros de Python sin dependencias externas.

```python
# src/domain/entities/purchase_order.py
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4


class POStatus(Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class Country(Enum):
    CL = "CL"
    NZ = "NZ"


@dataclass(frozen=True, kw_only=True)
class POItem:
    """Línea individual de una Purchase Order."""
    item_id: str
    product_name: str                    # ej: "Grapes Green Seedless"
    variety: str
    quantity_cases: int
    price_per_case: Decimal
    currency: str = "USD"

    def __post_init__(self):
        if self.quantity_cases <= 0:
            raise ValueError(f"quantity_cases debe ser > 0, recibido: {self.quantity_cases}")
        if self.price_per_case <= 0:
            raise ValueError(f"price_per_case debe ser > 0, recibido: {self.price_per_case}")

    @property
    def total_amount(self) -> Decimal:
        return self.price_per_case * self.quantity_cases


@dataclass(frozen=True, kw_only=True)
class PurchaseOrder:
    """Entidad raíz: Purchase Order de iTrade."""
    po_number: str
    buyer_name: str
    items: tuple[POItem, ...]            # tuple para inmutabilidad
    status: POStatus = POStatus.PENDING
    sales_order_number: Optional[str] = None
    country: Country = Country.CL       # Forzado CL por regla de negocio
    created_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        if not self.items:
            raise ValueError("PurchaseOrder debe tener al menos un item")
        # Regla de negocio: forzar país CL sobre NZ
        if self.country == Country.NZ:
            object.__setattr__(self, 'country', Country.CL)

    @property
    def total_cases(self) -> int:
        return sum(item.quantity_cases for item in self.items)

    @property
    def total_amount(self) -> Decimal:
        return sum(item.total_amount for item in self.items)

    @property
    def item_count(self) -> int:
        return len(self.items)

    def with_status(self, new_status: POStatus) -> "PurchaseOrder":
        """Retorna nueva instancia con status actualizado (inmutabilidad)."""
        return PurchaseOrder(
            po_number=self.po_number,
            buyer_name=self.buyer_name,
            items=self.items,
            status=new_status,
            sales_order_number=self.sales_order_number,
            country=self.country,
            created_at=self.created_at,
        )

    def with_sales_order(self, so_number: str) -> "PurchaseOrder":
        return PurchaseOrder(
            po_number=self.po_number,
            buyer_name=self.buyer_name,
            items=self.items,
            status=self.status,
            sales_order_number=so_number,
            country=self.country,
            created_at=self.created_at,
        )
```

```python
# src/domain/entities/shipment.py
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional


@dataclass(frozen=True, kw_only=True)
class Shipment:
    """Embarque con datos de peso y pallets para transición a In Transit."""
    shipment_id: str
    po_number: str
    container_number: Optional[str] = None
    total_weight_kg: Decimal
    pallet_count: int
    total_cases: int
    vessel_name: Optional[str] = None
    etd: Optional[date] = None          # Estimated Time of Departure
    eta: Optional[date] = None          # Estimated Time of Arrival

    def __post_init__(self):
        if self.pallet_count <= 0:
            raise ValueError("pallet_count debe ser > 0")
        if self.total_weight_kg <= 0:
            raise ValueError("total_weight_kg debe ser > 0")
```

```python
# src/domain/entities/invoice.py
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional


class InvoiceStatus(Enum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"    # HITL: esperando validación humana
    APPROVED = "approved"
    REJECTED = "rejected"
    PAID = "paid"


@dataclass(frozen=True, kw_only=True)
class InvoiceLine:
    """Línea de detalle de factura de transportista."""
    description: str
    reference_number: str                # Guía de despacho o BL
    amount: Decimal
    currency: str = "CLP"

    def __post_init__(self):
        if self.amount < 0:
            raise ValueError("amount no puede ser negativo")


@dataclass(frozen=True, kw_only=True)
class Invoice:
    """Factura de transportista."""
    invoice_number: str
    carrier_name: str
    invoice_date: date
    lines: tuple[InvoiceLine, ...]
    status: InvoiceStatus = InvoiceStatus.DRAFT
    due_date: Optional[date] = None

    @property
    def total_amount(self) -> Decimal:
        return sum(line.amount for line in self.lines)

    @property
    def line_count(self) -> int:
        return len(self.lines)

    def approve(self) -> "Invoice":
        """HITL: aprobación humana."""
        if self.status != InvoiceStatus.PENDING_REVIEW:
            raise ValueError(f"Solo se puede aprobar desde PENDING_REVIEW, actual: {self.status}")
        return Invoice(
            invoice_number=self.invoice_number,
            carrier_name=self.carrier_name,
            invoice_date=self.invoice_date,
            lines=self.lines,
            status=InvoiceStatus.APPROVED,
            due_date=self.due_date,
        )
```

```python
# src/domain/entities/pallet.py
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, kw_only=True)
class Pallet:
    """Pallet individual para generación de etiquetas."""
    pallet_number: int                   # 1 a 20 por contenedor
    container_number: str
    product_name: str
    variety: str
    grower_code: str
    case_count: int
    net_weight_kg: Decimal
    gross_weight_kg: Decimal
    destination_port: str
    buyer_name: str

    def __post_init__(self):
        if not 1 <= self.pallet_number <= 20:
            raise ValueError(f"pallet_number debe estar entre 1 y 20, recibido: {self.pallet_number}")
```

### 1.2 Casos de Uso

Cada caso de uso es un `@dataclass` con dependencias inyectadas y un método `execute()`.

```python
# src/application/use_cases/confirm_po.py
from dataclasses import dataclass
from src.domain.entities.purchase_order import PurchaseOrder, POStatus
from src.application.ports.itrade_gateway import ITradeGateway
from src.application.ports.po_repository import PORepository
from src.application.ports.master_sheet import MasterSheetWriter
from src.application.ports.logger import AppLogger


@dataclass(frozen=True)
class ConfirmMultiItemPOUseCase:
    """
    Caso de uso: Confirmar PO multi-item en iTrade.

    Flujo:
    1. Verificar idempotencia (¿ya confirmada?)
    2. Extraer items de la PO desde iTrade
    3. Validar reglas de dominio (NZ -> CL)
    4. Confirmar PO en iTrade
    5. Capturar Sales Order number
    6. Escribir 1 fila por item en el Maestro
    7. Descargar PDF de confirmación
    8. Registrar en log de reconciliación
    """
    itrade: ITradeGateway
    repo: PORepository
    master: MasterSheetWriter
    logger: AppLogger

    async def execute(self, po_number: str) -> PurchaseOrder:
        # 1. Idempotencia
        existing = await self.repo.find_by_po_number(po_number)
        if existing and existing.status != POStatus.PENDING:
            self.logger.info(f"PO {po_number} ya procesada (status={existing.status}), saltando")
            return existing

        # 2. Extraer datos de iTrade
        po = await self.itrade.extract_po(po_number)

        # 3. La entidad PO ya fuerza CL sobre NZ en __post_init__

        # 4. Confirmar en iTrade
        await self.itrade.confirm_po(po.po_number)

        # 5. Capturar SO
        so_number = await self.itrade.capture_sales_order(po.po_number)
        po = po.with_sales_order(so_number)
        po = po.with_status(POStatus.CONFIRMED)

        # 6. Escribir al maestro (1 fila por item)
        for item in po.items:
            await self.master.write_item_row(po, item)

        # 7. Descargar PDF
        await self.itrade.download_confirmation_pdf(po.po_number)

        # 8. Persistir estado
        await self.repo.save(po)

        self.logger.info(
            f"PO {po_number} confirmada: SO={so_number}, items={po.item_count}, "
            f"total={po.total_amount}"
        )
        return po
```

```python
# src/application/use_cases/transition_to_in_transit.py
@dataclass(frozen=True)
class TransitionToInTransitUseCase:
    """Pasar PO a estado In Transit con datos de embarque."""
    itrade: ITradeGateway
    repo: PORepository
    logger: AppLogger

    async def execute(self, po_number: str, shipment: Shipment) -> PurchaseOrder:
        po = await self.repo.find_by_po_number(po_number)
        if not po:
            raise ValueError(f"PO {po_number} no encontrada")
        if po.status == POStatus.IN_TRANSIT:
            self.logger.info(f"PO {po_number} ya en In Transit, saltando")
            return po

        await self.itrade.set_in_transit(
            po_number=po.po_number,
            weight_kg=shipment.total_weight_kg,
            pallet_count=shipment.pallet_count,
            country_code="CL",  # Siempre CL
        )

        po = po.with_status(POStatus.IN_TRANSIT)
        await self.repo.save(po)
        return po
```

```python
# src/application/use_cases/consolidate_invoices.py
@dataclass(frozen=True)
class ConsolidateInvoicesUseCase:
    """ETL: Consolidar facturas de transporte."""
    extractor: InvoiceExtractor
    validator: InvoiceValidator
    consolidator: InvoiceConsolidator
    output_writer: ConsolidatedOutputWriter
    reconciler: ReconciliationReporter
    logger: AppLogger

    async def execute(
        self,
        carrier_name: str,
        source_path: str,
        group_by: str = "invoice",  # "invoice" | "shipment"
    ) -> ConsolidationResult:
        # Extract
        raw_data = await self.extractor.extract(carrier_name, source_path)

        # Validate
        valid_rows, errors = await self.validator.validate(raw_data)
        if errors:
            self.logger.warning(f"{len(errors)} filas con errores de validación")

        # Transform + Group
        consolidated = await self.consolidator.consolidate(valid_rows, group_by)

        # Load
        await self.output_writer.write(consolidated)

        # Reconcile
        report = await self.reconciler.generate(
            source_count=len(raw_data),
            valid_count=len(valid_rows),
            error_count=len(errors),
            output_count=len(consolidated),
        )

        return ConsolidationResult(
            consolidated_data=consolidated,
            reconciliation=report,
            errors=errors,
        )
```

```python
# src/application/use_cases/generate_weekly_report.py
@dataclass(frozen=True)
class GenerateWeeklyShipStatusUseCase:
    """Reporte dominical: Weekly Ship Status para 10+ clientes."""
    data_source: ShipmentDataSource
    report_builder: WeeklyReportBuilder
    email_sender: EmailSender
    logger: AppLogger

    async def execute(self, week_date: date) -> list[str]:
        clients = await self.data_source.get_active_clients()
        sent_reports = []

        for client in clients:
            shipments = await self.data_source.get_shipments_for_client(
                client.client_id, week_date
            )
            report = await self.report_builder.build(client, shipments, week_date)
            await self.email_sender.send(
                to=client.email,
                subject=f"Weekly Ship Status - {week_date.isoformat()}",
                attachment=report,
            )
            sent_reports.append(client.client_id)

        self.logger.info(f"Weekly report enviado a {len(sent_reports)} clientes")
        return sent_reports
```

### 1.3 Contratos/Interfaces entre Capas (Ports)

Se usa `Protocol` (structural typing) en lugar de `ABC`. Razón: más flexible, Pythonic, no requiere herencia explícita.

```python
# src/application/ports/itrade_gateway.py
from typing import Protocol
from decimal import Decimal
from src.domain.entities.purchase_order import PurchaseOrder


class ITradeGateway(Protocol):
    """Puerto: operaciones contra iTrade (RPA o API)."""

    async def extract_po(self, po_number: str) -> PurchaseOrder:
        """Extrae datos de la PO incluyendo todos los items."""
        ...

    async def confirm_po(self, po_number: str) -> None:
        """Confirma la PO en iTrade."""
        ...

    async def capture_sales_order(self, po_number: str) -> str:
        """Captura el número de Sales Order post-confirmación."""
        ...

    async def set_in_transit(
        self,
        po_number: str,
        weight_kg: Decimal,
        pallet_count: int,
        country_code: str,
    ) -> None:
        """Transiciona PO a In Transit con datos de embarque."""
        ...

    async def download_confirmation_pdf(self, po_number: str) -> str:
        """Descarga PDF y retorna ruta del archivo."""
        ...
```

```python
# src/application/ports/po_repository.py
from typing import Protocol, Optional
from src.domain.entities.purchase_order import PurchaseOrder


class PORepository(Protocol):
    """Puerto: persistencia de estado de POs procesadas."""

    async def find_by_po_number(self, po_number: str) -> Optional[PurchaseOrder]:
        ...

    async def save(self, po: PurchaseOrder) -> None:
        ...

    async def list_by_status(self, status: str) -> list[PurchaseOrder]:
        ...
```

```python
# src/application/ports/invoice_extractor.py
from typing import Protocol
import pandas as pd


class InvoiceExtractor(Protocol):
    """Puerto: extracción de datos de facturas."""

    async def extract(self, carrier_name: str, source_path: str) -> pd.DataFrame:
        """Lee archivo Excel y retorna DataFrame con columnas estandarizadas."""
        ...


class InvoiceValidator(Protocol):
    """Puerto: validación de filas de factura."""

    async def validate(
        self, data: pd.DataFrame
    ) -> tuple[list, list[dict]]:
        """Retorna (filas_validas, errores)."""
        ...
```

```python
# src/application/ports/master_sheet.py
from typing import Protocol
from src.domain.entities.purchase_order import PurchaseOrder, POItem


class MasterSheetWriter(Protocol):
    """Puerto: escritura al Excel Maestro."""

    async def write_item_row(self, po: PurchaseOrder, item: POItem) -> None:
        """Escribe una fila por item en el Excel Maestro."""
        ...

    async def read_shipment_data(self, po_number: str) -> dict:
        """Lee datos de embarque desde el Maestro."""
        ...
```

### 1.4 Patrones Aplicables

| Patrón | Aplicación | Justificación |
|--------|-----------|---------------|
| **Repository** | `PORepository`, `InvoiceRepository` | Abstrae persistencia. Permite cambiar de Excel a DB sin tocar use cases. |
| **Adapter** | `PlaywrightITradeAdapter`, `PandasInvoiceExtractor` | Implementaciones concretas de los Ports. Desacopla infraestructura. |
| **Orchestrator** | `SmartbotsOrchestrator` | Coordina la ejecución secuencial de múltiples use cases en un run completo. |
| **Factory** | `CarrierAdapterFactory` | Crea el adaptador ETL correcto según el transportista. |
| **Strategy** | `GroupByInvoice`, `GroupByShipment` | Estrategia de agrupación configurable para ETL. |
| **Page Object Model** | `ITradeLoginPage`, `ITradePOPage` | Encapsula interacciones de Playwright por página. |

---

## 2. Estructuras Base

### 2.1 Árbol de Directorios Definitivo

```
smartbots-ecosystem/
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── .env.example                        # Template de variables de entorno
├── .gitignore
├── ruff.toml
│
├── configs/
│   ├── carriers/                       # Mapeos por transportista
│   │   ├── transporte_alfa.yaml
│   │   ├── transporte_beta.yaml
│   │   └── _schema.yaml               # Schema de referencia para mapeos
│   ├── business_rules.yaml             # Reglas NZ->CL, validaciones
│   └── clients.yaml                    # Clientes para Weekly Report
│
├── templates/
│   ├── pallet_tag.xlsx                 # Template de etiqueta de pallet
│   ├── planilla_carga.xlsx             # Template de planilla de carga
│   └── weekly_status.xlsx              # Template del reporte semanal
│
├── src/
│   ├── __init__.py
│   │
│   ├── domain/                         # === CAPA DE DOMINIO ===
│   │   ├── __init__.py
│   │   ├── entities/
│   │   │   ├── __init__.py
│   │   │   ├── purchase_order.py       # PurchaseOrder, POItem, POStatus
│   │   │   ├── shipment.py             # Shipment
│   │   │   ├── invoice.py              # Invoice, InvoiceLine, InvoiceStatus
│   │   │   └── pallet.py              # Pallet
│   │   ├── value_objects/
│   │   │   ├── __init__.py
│   │   │   ├── money.py                # Money(amount, currency)
│   │   │   └── country.py              # Country enum con validación
│   │   ├── exceptions.py               # Excepciones de dominio
│   │   └── services/
│   │       ├── __init__.py
│   │       ├── country_validator.py     # Lógica NZ -> CL
│   │       └── po_item_parser.py       # Parser 1-a-N
│   │
│   ├── application/                    # === CAPA DE APLICACIÓN ===
│   │   ├── __init__.py
│   │   ├── ports/                      # Interfaces (Protocols)
│   │   │   ├── __init__.py
│   │   │   ├── itrade_gateway.py
│   │   │   ├── po_repository.py
│   │   │   ├── invoice_extractor.py
│   │   │   ├── master_sheet.py
│   │   │   ├── report_builder.py
│   │   │   ├── email_sender.py
│   │   │   ├── pallet_tag_generator.py
│   │   │   └── logger.py
│   │   ├── use_cases/
│   │   │   ├── __init__.py
│   │   │   ├── confirm_po.py
│   │   │   ├── transition_to_in_transit.py
│   │   │   ├── consolidate_invoices.py
│   │   │   ├── generate_pallet_tags.py
│   │   │   ├── generate_load_sheet.py
│   │   │   └── generate_weekly_report.py
│   │   ├── dtos/
│   │   │   ├── __init__.py
│   │   │   ├── po_dtos.py              # Request/Response para PO
│   │   │   ├── invoice_dtos.py
│   │   │   └── report_dtos.py
│   │   └── orchestrator.py             # Orquestador principal
│   │
│   └── infrastructure/                 # === CAPA DE INFRAESTRUCTURA ===
│       ├── __init__.py
│       ├── rpa/                        # Adaptadores RPA (Playwright)
│       │   ├── __init__.py
│       │   ├── browser_manager.py      # Ciclo de vida del browser
│       │   ├── session_manager.py      # Auth state persistence
│       │   ├── pages/                  # Page Object Models
│       │   │   ├── __init__.py
│       │   │   ├── login_page.py
│       │   │   ├── po_list_page.py
│       │   │   ├── po_detail_page.py
│       │   │   └── in_transit_page.py
│       │   └── itrade_adapter.py       # Implementa ITradeGateway
│       ├── etl/                        # Adaptadores ETL
│       │   ├── __init__.py
│       │   ├── column_mapper.py        # Mapeo dinámico de columnas
│       │   ├── pandas_extractor.py     # Implementa InvoiceExtractor
│       │   ├── pydantic_validator.py   # Implementa InvoiceValidator
│       │   ├── consolidation_engine.py # Agrupación configurable
│       │   └── carrier_factory.py      # Factory de adaptadores
│       ├── excel/                      # Manejo de archivos Excel
│       │   ├── __init__.py
│       │   ├── master_sheet_adapter.py # Implementa MasterSheetWriter
│       │   ├── pallet_tag_writer.py
│       │   └── load_sheet_writer.py
│       ├── reporting/
│       │   ├── __init__.py
│       │   ├── weekly_builder.py       # Implementa WeeklyReportBuilder
│       │   └── reconciliation.py       # Reconciliation Report
│       ├── email/
│       │   ├── __init__.py
│       │   └── smtp_sender.py          # Implementa EmailSender
│       ├── persistence/
│       │   ├── __init__.py
│       │   └── json_po_repository.py   # Implementa PORepository (JSON/SQLite)
│       ├── logging/
│       │   ├── __init__.py
│       │   └── structured_logger.py    # Logging estructurado
│       └── config.py                   # Carga de configuración
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                     # Fixtures compartidas
│   ├── unit/
│   │   ├── __init__.py
│   │   ├── domain/
│   │   │   ├── test_purchase_order.py
│   │   │   ├── test_invoice.py
│   │   │   ├── test_pallet.py
│   │   │   └── test_country_validator.py
│   │   └── application/
│   │       ├── test_confirm_po.py
│   │       ├── test_consolidate_invoices.py
│   │       └── test_generate_weekly_report.py
│   ├── integration/
│   │   ├── __init__.py
│   │   ├── test_excel_handler.py
│   │   ├── test_etl_pipeline.py
│   │   └── test_json_repository.py
│   └── fixtures/
│       ├── sample_po.json
│       ├── sample_invoice_alfa.xlsx
│       └── sample_invoice_beta.xlsx
│
└── scripts/
    ├── run_po_cycle.py                 # Entry point: ciclo de POs
    ├── run_etl.py                      # Entry point: consolidación
    ├── run_weekly_report.py            # Entry point: reporte dominical
    └── run_pallet_tags.py              # Entry point: generación de tags
```

### 2.2 pyproject.toml

```toml
[project]
name = "smartbots-ecosystem"
version = "0.1.0"
description = "Ecosistema de Automatización RPA + ETL para Smartbots"
requires-python = ">=3.12"
dependencies = [
    "playwright>=1.49",
    "pandas>=2.2",
    "pydantic>=2.10",
    "openpyxl>=3.1",
    "pyyaml>=6.0",
    "tenacity>=9.0",
    "structlog>=24.4",
    "python-dotenv>=1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "pytest-cov>=6.0",
    "ruff>=0.9",
    "mypy>=1.14",
    "pandas-stubs>=2.2",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = [
    "E",      # pycodestyle errors
    "W",      # pycodestyle warnings
    "F",      # pyflakes
    "I",      # isort
    "N",      # pep8-naming
    "UP",     # pyupgrade
    "S",      # flake8-bandit (security)
    "B",      # flake8-bugbear
    "A",      # flake8-builtins
    "C4",     # flake8-comprehensions
    "DTZ",    # flake8-datetimez
    "RUF",    # ruff-specific
]
ignore = [
    "S101",   # assert en tests
]

[tool.ruff.lint.isort]
known-first-party = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = "--strict-markers --tb=short -q"
markers = [
    "integration: tests que requieren I/O real",
    "slow: tests que toman >5s",
]

[tool.mypy]
python_version = "3.12"
strict = true
warn_return_any = true
warn_unused_configs = true
```

### 2.3 Configuración (.env + configs)

```bash
# .env.example
# === iTrade ===
ITRADE_URL=https://www.itradenetwork.com
ITRADE_USERNAME=usuario
ITRADE_PASSWORD=secreto

# === Email (Weekly Report) ===
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=smartbots@empresa.cl
SMTP_PASSWORD=secreto

# === Rutas ===
MASTER_SHEET_PATH=/ruta/a/maestro.xlsx
OUTPUT_DIR=/ruta/a/output
PDF_DOWNLOAD_DIR=/ruta/a/pdfs
TEMPLATES_DIR=./templates

# === Comportamiento ===
HEADLESS=true
LOG_LEVEL=INFO
MAX_RETRIES=3
```

```yaml
# configs/carriers/transporte_alfa.yaml
carrier_name: "Transporte Alfa"
file_pattern: "factura_alfa_*.xlsx"
skip_rows: 2
sheet_name: "Detalle"

column_mapping:
  invoice_number: "N° Factura"
  invoice_date: "Fecha Emisión"
  reference_number: "N° Guía"
  description: "Detalle Servicio"
  amount: "Monto Total"
  currency: "Moneda"

date_format: "%d-%m-%Y"

validation_rules:
  amount_must_be_positive: true
  require_reference: true

aggregation:
  default_group_by: "invoice"           # "invoice" | "shipment"
  sum_fields: ["amount"]
  first_fields: ["invoice_date", "carrier_name"]
```

### 2.4 Convenciones de Código

| Aspecto | Convención |
|---------|-----------|
| **Naming** | snake_case para todo. Clases en PascalCase. |
| **Imports** | Absolutos desde `src.`. Ordenados por isort (ruff). |
| **Entidades** | `@dataclass(frozen=True, kw_only=True)`. Sin Pydantic en dominio. |
| **DTOs** | `pydantic.BaseModel` con `model_config = ConfigDict(frozen=True)`. |
| **Ports** | `typing.Protocol`. Un archivo por puerto. |
| **Use Cases** | `@dataclass(frozen=True)` con método `execute()`. |
| **Excepciones** | Dominio hereda de `SmartbotsError`. Nunca exceptions genéricas. |
| **Async** | Todos los ports y use cases son `async`. |
| **Type hints** | Obligatorios en todo. `mypy --strict`. |
| **Docstrings** | Google style. Solo en métodos públicos. |
| **Tests** | Prefijo `test_`. Un archivo de test por módulo. |

---

## 3. Modelado del Flujo RPA 1-a-N

### 3.1 Parseo Multi-Item

El parseo 1-a-N se modela como un servicio de dominio que convierte datos crudos de iTrade en una `PurchaseOrder` con N items:

```python
# src/domain/services/po_item_parser.py
from dataclasses import dataclass
from decimal import Decimal
from src.domain.entities.purchase_order import PurchaseOrder, POItem, Country


@dataclass(frozen=True)
class RawPOData:
    """Datos crudos extraídos de iTrade antes de parseo."""
    po_number: str
    buyer_name: str
    country_code: str
    items_raw: list[dict]   # Filas de la tabla HTML


def parse_po_from_raw(raw: RawPOData) -> PurchaseOrder:
    """
    Convierte datos crudos de iTrade en entidad PurchaseOrder.
    
    Cada fila de items_raw genera un POItem.
    La PO resultante tiene N items (relación 1-a-N).
    """
    items = tuple(
        POItem(
            item_id=row.get("item_id", f"{raw.po_number}-{i}"),
            product_name=row["product"],
            variety=row.get("variety", ""),
            quantity_cases=int(row["cases"]),
            price_per_case=Decimal(str(row["price"])),
            currency=row.get("currency", "USD"),
        )
        for i, row in enumerate(raw.items_raw, start=1)
    )

    return PurchaseOrder(
        po_number=raw.po_number,
        buyer_name=raw.buyer_name,
        items=items,
        country=Country(raw.country_code),  # __post_init__ corrige NZ -> CL
    )
```

En el Page Object del adaptador RPA, la extracción de la tabla multi-item:

```python
# src/infrastructure/rpa/pages/po_detail_page.py
from playwright.sync_api import Page


class PODetailPage:
    def __init__(self, page: Page):
        self.page = page
        self.items_table = page.locator("table.po-items")
        self.confirm_button = page.locator("button:has-text('Confirm')")
        self.so_number_field = page.locator(".sales-order-number")

    def extract_items(self) -> list[dict]:
        """Extrae todas las filas de la tabla de items (parseo 1-a-N)."""
        rows = self.items_table.locator("tbody tr").all()
        items = []
        for row in rows:
            cells = row.locator("td").all()
            items.append({
                "item_id": cells[0].text_content().strip(),
                "product": cells[1].text_content().strip(),
                "variety": cells[2].text_content().strip(),
                "cases": cells[3].text_content().strip(),
                "price": cells[4].text_content().strip().replace(",", ""),
                "currency": cells[5].text_content().strip() if len(cells) > 5 else "USD",
            })
        return items

    def confirm(self) -> None:
        self.confirm_button.click()
        self.page.wait_for_selector(".confirmation-success", state="visible", timeout=15000)

    def get_sales_order_number(self) -> str:
        return self.so_number_field.text_content().strip()
```

### 3.2 Idempotencia

Estrategia en tres niveles:

```
┌─────────────────────────────────────────────┐
│ Nivel 1: Estado persistido                  │
│ PORepository.find_by_po_number() != None    │
│ → Si status != PENDING, skip               │
├─────────────────────────────────────────────┤
│ Nivel 2: Verificación en UI                │
│ Antes de confirmar, verificar que PO en     │
│ iTrade aún está en estado "Open"            │
│ → Si ya "Confirmed", capturar SO y skip     │
├─────────────────────────────────────────────┤
│ Nivel 3: Log de operaciones                │
│ JSON append-only con hash de operación      │
│ hash(po_number + action + timestamp_day)    │
│ → Protección contra re-ejecución intra-día  │
└─────────────────────────────────────────────┘
```

```python
# src/infrastructure/persistence/json_po_repository.py
import json
import hashlib
from pathlib import Path
from typing import Optional
from src.domain.entities.purchase_order import PurchaseOrder, POStatus


class JsonPORepository:
    """Implementa PORepository usando JSON para persistencia ligera."""

    def __init__(self, storage_path: Path):
        self.storage_path = storage_path
        self.storage_path.mkdir(parents=True, exist_ok=True)

    async def find_by_po_number(self, po_number: str) -> Optional[PurchaseOrder]:
        file = self.storage_path / f"{po_number}.json"
        if not file.exists():
            return None
        data = json.loads(file.read_text())
        return self._deserialize(data)

    async def save(self, po: PurchaseOrder) -> None:
        file = self.storage_path / f"{po.po_number}.json"
        file.write_text(json.dumps(self._serialize(po), indent=2, default=str))

    def _generate_idempotency_key(self, po_number: str, action: str) -> str:
        """Hash determinístico para check de idempotencia."""
        from datetime import date
        content = f"{po_number}:{action}:{date.today().isoformat()}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]
```

### 3.3 Validación NZ → CL en Dominio

La corrección vive en la entidad `PurchaseOrder.__post_init__()` (ver sección 1.1). El dominio **nunca** permite que una PO tenga `country=NZ`:

```python
# Ya definido en PurchaseOrder.__post_init__:
if self.country == Country.NZ:
    object.__setattr__(self, 'country', Country.CL)
```

Adicionalmente, un servicio de dominio para validaciones complejas:

```python
# src/domain/services/country_validator.py
from src.domain.entities.purchase_order import Country
from src.domain.exceptions import CountryCorrectionApplied


def validate_and_correct_country(country_code: str) -> Country:
    """
    Regla de negocio: NZ debe ser CL.
    
    Raises CountryCorrectionApplied si se aplicó corrección (para logging).
    """
    if country_code.upper() == "NZ":
        raise CountryCorrectionApplied(
            original="NZ",
            corrected="CL",
            reason="Regla de negocio: Chile opera como CL, no NZ",
        )
    return Country(country_code.upper())
```

### 3.4 Manejo de Errores y Reintentos

```python
# src/infrastructure/rpa/browser_manager.py
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)
import structlog

logger = structlog.get_logger()


@dataclass
class BrowserConfig:
    headless: bool = True
    timeout_ms: int = 30_000
    max_retries: int = 3
    auth_state_path: Path = Path("auth_states")
    failure_output_dir: Path = Path("failures")


class BrowserManager:
    """Gestión del ciclo de vida del browser con captura de fallos."""

    def __init__(self, config: BrowserConfig):
        self.config = config
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

    def __enter__(self):
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self.config.headless)
        self._context = self._setup_context()
        # Iniciar tracing para captura en caso de error
        self._context.tracing.start(screenshots=True, snapshots=True)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self._capture_failure(exc_val)
        if self._context:
            self._save_auth_state()
            self._context.tracing.stop()
            self._context.close()
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()

    def new_page(self) -> Page:
        page = self._context.new_page()
        page.set_default_timeout(self.config.timeout_ms)
        return page

    def _setup_context(self) -> BrowserContext:
        state_file = self.config.auth_state_path / "itrade_state.json"
        kwargs = {"viewport": {"width": 1920, "height": 1080}}
        if state_file.exists():
            kwargs["storage_state"] = str(state_file)
            logger.info("auth_state_loaded", path=str(state_file))
        return self._browser.new_context(**kwargs)

    def _save_auth_state(self) -> None:
        state_file = self.config.auth_state_path / "itrade_state.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)
        self._context.storage_state(path=str(state_file))

    def _capture_failure(self, error: Exception) -> None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = self.config.failure_output_dir
        out.mkdir(parents=True, exist_ok=True)

        # Trace (abre en https://trace.playwright.dev)
        self._context.tracing.stop(path=out / f"trace_{ts}.zip")

        # Screenshot de cada página abierta
        for i, page in enumerate(self._context.pages):
            page.screenshot(path=out / f"screenshot_{ts}_p{i}.png", full_page=True)
            (out / f"page_{ts}_p{i}.html").write_text(page.content())

        logger.error("rpa_failure_captured", error=str(error), output_dir=str(out))
```

Decorador de reintento para operaciones RPA:

```python
# src/infrastructure/rpa/retry.py
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)
from playwright.sync_api import TimeoutError as PlaywrightTimeout
import structlog

logger = structlog.get_logger()


def rpa_retry(max_attempts: int = 3):
    """Decorador de reintento para operaciones RPA."""
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        retry=retry_if_exception_type((PlaywrightTimeout, ConnectionError)),
        before_sleep=before_sleep_log(logger, "WARNING"),
        reraise=True,
    )
```

---

## 4. Diseño del ETL Configurable

### 4.1 Sistema de Mapeo Dinámico por Transportista

```python
# src/infrastructure/etl/column_mapper.py
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import yaml
import pandas as pd


@dataclass(frozen=True)
class CarrierMapping:
    """Configuración de mapeo para un transportista."""
    carrier_name: str
    file_pattern: str
    skip_rows: int
    sheet_name: str
    column_mapping: dict[str, str]       # standard_name -> carrier_column_name
    date_format: str
    validation_rules: dict[str, bool]
    aggregation: dict[str, str | list[str]]

    @classmethod
    def from_yaml(cls, path: Path) -> "CarrierMapping":
        data = yaml.safe_load(path.read_text())
        return cls(
            carrier_name=data["carrier_name"],
            file_pattern=data["file_pattern"],
            skip_rows=data.get("skip_rows", 0),
            sheet_name=data.get("sheet_name", "Sheet1"),
            column_mapping=data["column_mapping"],
            date_format=data.get("date_format", "%Y-%m-%d"),
            validation_rules=data.get("validation_rules", {}),
            aggregation=data.get("aggregation", {}),
        )

    @property
    def reverse_mapping(self) -> dict[str, str]:
        """carrier_column -> standard_column para renombrar."""
        return {v: k for k, v in self.column_mapping.items()}


class ColumnMapper:
    """Aplica mapeo dinámico de columnas sobre un DataFrame."""

    def __init__(self, mappings_dir: Path):
        self.mappings: dict[str, CarrierMapping] = {}
        self._load_all_mappings(mappings_dir)

    def _load_all_mappings(self, mappings_dir: Path) -> None:
        for yaml_file in mappings_dir.glob("*.yaml"):
            if yaml_file.name.startswith("_"):
                continue  # Skip schema files
            mapping = CarrierMapping.from_yaml(yaml_file)
            self.mappings[mapping.carrier_name.lower()] = mapping

    def standardize(self, df: pd.DataFrame, carrier_name: str) -> pd.DataFrame:
        """Renombra columnas del carrier a nombres estándar."""
        mapping = self._get_mapping(carrier_name)
        return df.rename(columns=mapping.reverse_mapping)

    def _get_mapping(self, carrier_name: str) -> CarrierMapping:
        key = carrier_name.lower()
        if key not in self.mappings:
            available = ", ".join(self.mappings.keys())
            raise ValueError(
                f"No hay mapeo para carrier '{carrier_name}'. "
                f"Disponibles: {available}"
            )
        return self.mappings[key]
```

### 4.2 Estrategia de Agrupación Configurable

```python
# src/infrastructure/etl/consolidation_engine.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
import pandas as pd


class GroupingStrategy(ABC):
    """Estrategia de agrupación para consolidación."""

    @abstractmethod
    def group(self, df: pd.DataFrame) -> pd.DataFrame:
        ...


class GroupByInvoice(GroupingStrategy):
    """Opción A: Una línea por factura (totalizada)."""

    def group(self, df: pd.DataFrame) -> pd.DataFrame:
        return df.groupby("invoice_number").agg({
            "invoice_date": "first",
            "carrier_name": "first",
            "amount": "sum",
            "reference_number": lambda x: ", ".join(x.unique()),
            "description": lambda x: f"{len(x)} servicios",
        }).reset_index()


class GroupByShipment(GroupingStrategy):
    """Opción B: Una línea por embarque/guía."""

    def group(self, df: pd.DataFrame) -> pd.DataFrame:
        return df.groupby("reference_number").agg({
            "invoice_number": "first",
            "invoice_date": "first",
            "carrier_name": "first",
            "amount": "sum",
            "description": "first",
        }).reset_index()


STRATEGIES: dict[str, type[GroupingStrategy]] = {
    "invoice": GroupByInvoice,
    "shipment": GroupByShipment,
}


def get_grouping_strategy(name: str) -> GroupingStrategy:
    """Factory para obtener la estrategia de agrupación."""
    if name not in STRATEGIES:
        raise ValueError(f"Estrategia '{name}' no existe. Opciones: {list(STRATEGIES.keys())}")
    return STRATEGIES[name]()
```

### 4.3 Validación de Esquemas con Pydantic

```python
# src/infrastructure/etl/pydantic_validator.py
from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field, field_validator, ConfigDict, TypeAdapter
import pandas as pd
import structlog

logger = structlog.get_logger()


class InvoiceRowSchema(BaseModel):
    """Schema Pydantic para validación de fila de factura."""
    model_config = ConfigDict(frozen=True)

    invoice_number: str = Field(min_length=1)
    invoice_date: datetime
    reference_number: str = Field(min_length=1)
    description: str
    amount: Decimal = Field(gt=0)
    currency: str = Field(default="CLP")

    @field_validator("amount", mode="before")
    @classmethod
    def parse_amount(cls, v):
        if isinstance(v, str):
            v = v.replace("$", "").replace(".", "").replace(",", ".").strip()
        return Decimal(str(v))

    @field_validator("invoice_date", mode="before")
    @classmethod
    def parse_date(cls, v):
        if isinstance(v, str):
            for fmt in ["%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"]:
                try:
                    return datetime.strptime(v, fmt)
                except ValueError:
                    continue
            raise ValueError(f"Formato de fecha no reconocido: {v}")
        return v


class PydanticInvoiceValidator:
    """Validador que aplica esquema Pydantic fila por fila."""

    def __init__(self):
        self._adapter = TypeAdapter(InvoiceRowSchema)

    async def validate(
        self, df: pd.DataFrame
    ) -> tuple[list[InvoiceRowSchema], list[dict]]:
        valid_rows: list[InvoiceRowSchema] = []
        errors: list[dict] = []

        for idx, row in df.iterrows():
            try:
                validated = self._adapter.validate_python(row.to_dict())
                valid_rows.append(validated)
            except Exception as e:
                errors.append({
                    "row_index": idx,
                    "error": str(e),
                    "row_data": {k: str(v) for k, v in row.to_dict().items()},
                })
                logger.warning(
                    "validation_error",
                    row_index=idx,
                    error=str(e),
                )

        logger.info(
            "validation_complete",
            total=len(df),
            valid=len(valid_rows),
            errors=len(errors),
        )
        return valid_rows, errors
```

### 4.4 Reconciliación de Datos

```python
# src/infrastructure/reporting/reconciliation.py
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
import structlog

logger = structlog.get_logger()


class DiscrepancyType(Enum):
    ROW_COUNT_MISMATCH = "row_count_mismatch"
    AMOUNT_MISMATCH = "amount_mismatch"
    MISSING_IN_OUTPUT = "missing_in_output"
    VALIDATION_FAILURE = "validation_failure"


@dataclass
class Discrepancy:
    type: DiscrepancyType
    description: str
    expected: str
    actual: str
    severity: str = "WARNING"   # WARNING | ERROR | CRITICAL


@dataclass
class ReconciliationReport:
    """Reporte de reconciliación post-procesamiento."""
    run_id: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    source_name: str = ""
    source_row_count: int = 0
    valid_row_count: int = 0
    error_row_count: int = 0
    output_row_count: int = 0
    source_total_amount: Decimal = Decimal("0")
    output_total_amount: Decimal = Decimal("0")
    discrepancies: list[Discrepancy] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return len(self.discrepancies) == 0

    @property
    def data_loss_pct(self) -> float:
        if self.source_row_count == 0:
            return 0.0
        processed = self.valid_row_count + self.error_row_count
        if processed != self.source_row_count:
            return ((self.source_row_count - processed) / self.source_row_count) * 100
        return 0.0

    @property
    def amount_variance(self) -> Decimal:
        return abs(self.source_total_amount - self.output_total_amount)

    def add_discrepancy(self, disc: Discrepancy) -> None:
        self.discrepancies.append(disc)
        logger.warning(
            "reconciliation_discrepancy",
            type=disc.type.value,
            description=disc.description,
            severity=disc.severity,
        )

    def validate_zero_data_loss(self) -> None:
        """Valida objetivo de 0% data loss."""
        total_accounted = self.valid_row_count + self.error_row_count
        if total_accounted != self.source_row_count:
            self.add_discrepancy(Discrepancy(
                type=DiscrepancyType.ROW_COUNT_MISMATCH,
                description="Filas no contabilizadas detectadas",
                expected=str(self.source_row_count),
                actual=str(total_accounted),
                severity="CRITICAL",
            ))

        if self.amount_variance > Decimal("0.01"):
            self.add_discrepancy(Discrepancy(
                type=DiscrepancyType.AMOUNT_MISMATCH,
                description="Varianza de montos detectada",
                expected=str(self.source_total_amount),
                actual=str(self.output_total_amount),
                severity="CRITICAL",
            ))

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "timestamp": self.timestamp.isoformat(),
            "source_name": self.source_name,
            "source_row_count": self.source_row_count,
            "valid_row_count": self.valid_row_count,
            "error_row_count": self.error_row_count,
            "output_row_count": self.output_row_count,
            "data_loss_pct": self.data_loss_pct,
            "amount_variance": str(self.amount_variance),
            "is_clean": self.is_clean,
            "discrepancies": [
                {
                    "type": d.type.value,
                    "description": d.description,
                    "expected": d.expected,
                    "actual": d.actual,
                    "severity": d.severity,
                }
                for d in self.discrepancies
            ],
        }
```

---

## 5. Estrategia de Testing

### 5.1 Unit Tests del Dominio

```python
# tests/unit/domain/test_purchase_order.py
from decimal import Decimal
import pytest
from src.domain.entities.purchase_order import (
    PurchaseOrder, POItem, POStatus, Country,
)


class TestPOItem:
    def test_total_amount_calculation(self):
        item = POItem(
            item_id="1",
            product_name="Grapes",
            variety="Green Seedless",
            quantity_cases=100,
            price_per_case=Decimal("25.50"),
        )
        assert item.total_amount == Decimal("2550.00")

    def test_rejects_zero_quantity(self):
        with pytest.raises(ValueError, match="quantity_cases debe ser > 0"):
            POItem(
                item_id="1",
                product_name="Grapes",
                variety="Green",
                quantity_cases=0,
                price_per_case=Decimal("10"),
            )

    def test_rejects_negative_price(self):
        with pytest.raises(ValueError, match="price_per_case debe ser > 0"):
            POItem(
                item_id="1",
                product_name="Grapes",
                variety="Green",
                quantity_cases=10,
                price_per_case=Decimal("-5"),
            )


class TestPurchaseOrder:
    @pytest.fixture
    def sample_items(self):
        return (
            POItem(item_id="1", product_name="Grapes Green", variety="Seedless",
                   quantity_cases=100, price_per_case=Decimal("25.50")),
            POItem(item_id="2", product_name="Grapes Red", variety="Globe",
                   quantity_cases=50, price_per_case=Decimal("30.00")),
        )

    def test_country_nz_corrected_to_cl(self, sample_items):
        """Regla de negocio crítica: NZ siempre se corrige a CL."""
        po = PurchaseOrder(
            po_number="PO-001",
            buyer_name="Test Buyer",
            items=sample_items,
            country=Country.NZ,  # Intenta NZ
        )
        assert po.country == Country.CL  # Forzado a CL

    def test_total_cases(self, sample_items):
        po = PurchaseOrder(
            po_number="PO-001",
            buyer_name="Test",
            items=sample_items,
        )
        assert po.total_cases == 150

    def test_total_amount(self, sample_items):
        po = PurchaseOrder(
            po_number="PO-001",
            buyer_name="Test",
            items=sample_items,
        )
        assert po.total_amount == Decimal("4050.00")

    def test_with_status_returns_new_instance(self, sample_items):
        po = PurchaseOrder(po_number="PO-001", buyer_name="Test", items=sample_items)
        updated = po.with_status(POStatus.CONFIRMED)
        assert po.status == POStatus.PENDING           # Original sin cambio
        assert updated.status == POStatus.CONFIRMED     # Nueva instancia

    def test_rejects_empty_items(self):
        with pytest.raises(ValueError, match="al menos un item"):
            PurchaseOrder(po_number="PO-001", buyer_name="Test", items=())

    def test_immutability(self, sample_items):
        po = PurchaseOrder(po_number="PO-001", buyer_name="Test", items=sample_items)
        with pytest.raises(AttributeError):
            po.status = POStatus.CONFIRMED
```

### 5.2 Mocks del Adaptador RPA

```python
# tests/unit/application/test_confirm_po.py
from dataclasses import dataclass
from decimal import Decimal
from unittest.mock import AsyncMock
import pytest
from src.domain.entities.purchase_order import PurchaseOrder, POItem, POStatus
from src.application.use_cases.confirm_po import ConfirmMultiItemPOUseCase


@pytest.fixture
def mock_po():
    return PurchaseOrder(
        po_number="PO-TEST-001",
        buyer_name="Test Buyer",
        items=(
            POItem(item_id="1", product_name="Grapes", variety="Green",
                   quantity_cases=100, price_per_case=Decimal("25")),
        ),
    )


@pytest.fixture
def mock_itrade(mock_po):
    gateway = AsyncMock()
    gateway.extract_po.return_value = mock_po
    gateway.capture_sales_order.return_value = "SO-12345"
    gateway.confirm_po.return_value = None
    gateway.download_confirmation_pdf.return_value = "/tmp/PO-TEST-001.pdf"
    return gateway


@pytest.fixture
def mock_repo():
    repo = AsyncMock()
    repo.find_by_po_number.return_value = None  # No existe -> no es idempotente
    return repo


@pytest.fixture
def mock_master():
    return AsyncMock()


@pytest.fixture
def mock_logger():
    return AsyncMock()


class TestConfirmMultiItemPO:
    async def test_confirms_new_po(self, mock_itrade, mock_repo, mock_master, mock_logger):
        uc = ConfirmMultiItemPOUseCase(
            itrade=mock_itrade,
            repo=mock_repo,
            master=mock_master,
            logger=mock_logger,
        )
        result = await uc.execute("PO-TEST-001")

        assert result.status == POStatus.CONFIRMED
        assert result.sales_order_number == "SO-12345"
        mock_itrade.confirm_po.assert_awaited_once_with("PO-TEST-001")
        mock_master.write_item_row.assert_awaited_once()  # 1 item = 1 llamada
        mock_repo.save.assert_awaited_once()

    async def test_skips_already_confirmed_po(
        self, mock_itrade, mock_repo, mock_master, mock_logger, mock_po
    ):
        """Idempotencia: si PO ya está confirmada, no se re-procesa."""
        confirmed_po = mock_po.with_status(POStatus.CONFIRMED)
        mock_repo.find_by_po_number.return_value = confirmed_po

        uc = ConfirmMultiItemPOUseCase(
            itrade=mock_itrade,
            repo=mock_repo,
            master=mock_master,
            logger=mock_logger,
        )
        result = await uc.execute("PO-TEST-001")

        assert result.status == POStatus.CONFIRMED
        mock_itrade.confirm_po.assert_not_awaited()  # NO se llamó a iTrade
        mock_master.write_item_row.assert_not_awaited()

    async def test_writes_one_row_per_item(
        self, mock_itrade, mock_repo, mock_master, mock_logger
    ):
        """Multi-item: debe escribir N filas en el maestro."""
        multi_item_po = PurchaseOrder(
            po_number="PO-MULTI",
            buyer_name="Test",
            items=(
                POItem(item_id="1", product_name="Grapes", variety="Green",
                       quantity_cases=50, price_per_case=Decimal("25")),
                POItem(item_id="2", product_name="Cherries", variety="Bing",
                       quantity_cases=30, price_per_case=Decimal("40")),
                POItem(item_id="3", product_name="Blueberries", variety="Duke",
                       quantity_cases=20, price_per_case=Decimal("60")),
            ),
        )
        mock_itrade.extract_po.return_value = multi_item_po
        mock_repo.find_by_po_number.return_value = None

        uc = ConfirmMultiItemPOUseCase(
            itrade=mock_itrade, repo=mock_repo,
            master=mock_master, logger=mock_logger,
        )
        await uc.execute("PO-MULTI")

        assert mock_master.write_item_row.await_count == 3  # 3 items = 3 filas
```

### 5.3 Pruebas de Integración

```python
# tests/integration/test_etl_pipeline.py
from pathlib import Path
import pytest
from src.infrastructure.etl.column_mapper import ColumnMapper
from src.infrastructure.etl.pydantic_validator import PydanticInvoiceValidator
from src.infrastructure.etl.consolidation_engine import get_grouping_strategy


@pytest.mark.integration
class TestETLPipeline:
    @pytest.fixture
    def sample_file(self):
        return Path("tests/fixtures/sample_invoice_alfa.xlsx")

    @pytest.fixture
    def mapper(self):
        return ColumnMapper(Path("configs/carriers"))

    async def test_full_pipeline_by_invoice(self, sample_file, mapper):
        """Pipeline completo: extract -> validate -> group by invoice."""
        import pandas as pd

        # Extract
        df = pd.read_excel(sample_file, skiprows=2)
        df = mapper.standardize(df, "Transporte Alfa")

        # Validate
        validator = PydanticInvoiceValidator()
        valid, errors = await validator.validate(df)

        assert len(valid) > 0
        assert len(errors) == 0

        # Group
        valid_df = pd.DataFrame([r.model_dump() for r in valid])
        strategy = get_grouping_strategy("invoice")
        result = strategy.group(valid_df)

        assert len(result) <= len(valid_df)  # Agrupado = menos filas
```

### 5.4 Validaciones Financieras Críticas

```python
# tests/unit/domain/test_financial_validations.py
from decimal import Decimal
import pytest
from src.infrastructure.reporting.reconciliation import (
    ReconciliationReport, Discrepancy, DiscrepancyType,
)


class TestReconciliationReport:
    def test_zero_data_loss_passes(self):
        report = ReconciliationReport(
            run_id="test-001",
            source_row_count=100,
            valid_row_count=95,
            error_row_count=5,
            source_total_amount=Decimal("50000.00"),
            output_total_amount=Decimal("50000.00"),
        )
        report.validate_zero_data_loss()
        assert report.is_clean

    def test_detects_unaccounted_rows(self):
        report = ReconciliationReport(
            run_id="test-002",
            source_row_count=100,
            valid_row_count=90,
            error_row_count=5,    # 90 + 5 = 95, no 100 -> 5 filas perdidas
            source_total_amount=Decimal("50000"),
            output_total_amount=Decimal("50000"),
        )
        report.validate_zero_data_loss()
        assert not report.is_clean
        assert any(d.severity == "CRITICAL" for d in report.discrepancies)

    def test_detects_amount_variance(self):
        report = ReconciliationReport(
            run_id="test-003",
            source_row_count=100,
            valid_row_count=100,
            error_row_count=0,
            source_total_amount=Decimal("50000.00"),
            output_total_amount=Decimal("49500.00"),  # $500 de diferencia
        )
        report.validate_zero_data_loss()
        assert not report.is_clean
        assert report.amount_variance == Decimal("500.00")

    def test_po_total_matches_sum_of_items(self):
        """Validación cruzada: total de PO = suma de items."""
        from src.domain.entities.purchase_order import PurchaseOrder, POItem

        items = (
            POItem(item_id="1", product_name="A", variety="X",
                   quantity_cases=100, price_per_case=Decimal("10.00")),
            POItem(item_id="2", product_name="B", variety="Y",
                   quantity_cases=50, price_per_case=Decimal("20.00")),
        )
        po = PurchaseOrder(po_number="PO-FIN", buyer_name="Test", items=items)

        expected = Decimal("1000.00") + Decimal("1000.00")
        assert po.total_amount == expected
        assert po.total_amount == sum(item.total_amount for item in po.items)
```

---

## 6. Estrategia de Observabilidad

### 6.1 Logging Estructurado

```python
# src/infrastructure/logging/structured_logger.py
import structlog
from pathlib import Path


def setup_logging(log_level: str = "INFO", log_file: Path | None = None) -> None:
    """Configura logging estructurado con structlog."""
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if log_file:
        # JSON para archivos (machine-readable)
        processors.append(structlog.processors.JSONRenderer())
    else:
        # Console-friendly para desarrollo
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            structlog.get_level_from_name(log_level)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
```

Uso en el sistema:

```python
import structlog

logger = structlog.get_logger()

# Contexto automático por ejecución
structlog.contextvars.bind_contextvars(
    run_id="run-2026-02-11-001",
    module="rpa_itrade",
)

# Logs contextuales
logger.info("po_processing_started", po_number="PO-123", items=3)
logger.info("po_confirmed", po_number="PO-123", so_number="SO-456")
logger.warning("country_corrected", original="NZ", corrected="CL", po="PO-123")
logger.error("rpa_timeout", page="po_detail", timeout_ms=30000)
```

Formato de salida JSON (para logs/):
```json
{
  "timestamp": "2026-02-11T08:15:00Z",
  "level": "info",
  "event": "po_confirmed",
  "run_id": "run-2026-02-11-001",
  "module": "rpa_itrade",
  "po_number": "PO-123",
  "so_number": "SO-456"
}
```

### 6.2 Generación Automática de Reconciliation Report

El `ReconciliationReport` (sección 4.4) se genera al final de cada ejecución del orquestador:

```python
# src/application/orchestrator.py
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import json
import structlog

logger = structlog.get_logger()


@dataclass
class SmartbotsOrchestrator:
    """Orquestador principal: ejecuta ciclos completos con reconciliación."""

    confirm_po_uc: ConfirmMultiItemPOUseCase
    transition_uc: TransitionToInTransitUseCase
    consolidate_uc: ConsolidateInvoicesUseCase
    output_dir: Path

    async def run_po_cycle(self, po_numbers: list[str]) -> ReconciliationReport:
        run_id = f"po-cycle-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
        structlog.contextvars.bind_contextvars(run_id=run_id)

        report = ReconciliationReport(run_id=run_id, source_name="iTrade PO Cycle")
        report.source_row_count = len(po_numbers)

        for po_number in po_numbers:
            try:
                result = await self.confirm_po_uc.execute(po_number)
                report.valid_row_count += 1
                logger.info("po_processed", po_number=po_number, status=result.status.value)
            except Exception as e:
                report.error_row_count += 1
                report.add_discrepancy(Discrepancy(
                    type=DiscrepancyType.VALIDATION_FAILURE,
                    description=f"Error procesando PO {po_number}: {e}",
                    expected="success",
                    actual="error",
                    severity="ERROR",
                ))
                logger.error("po_processing_failed", po_number=po_number, error=str(e))

        report.validate_zero_data_loss()
        self._save_report(report)
        return report

    def _save_report(self, report: ReconciliationReport) -> None:
        report_path = self.output_dir / f"reconciliation_{report.run_id}.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report.to_dict(), indent=2))
        logger.info(
            "reconciliation_report_saved",
            path=str(report_path),
            is_clean=report.is_clean,
            data_loss_pct=report.data_loss_pct,
        )
```

### 6.3 Alertas por Error Crítico

```python
# src/infrastructure/email/alert_sender.py
from dataclasses import dataclass
from src.infrastructure.reporting.reconciliation import ReconciliationReport
import structlog

logger = structlog.get_logger()


@dataclass(frozen=True)
class AlertConfig:
    alert_email: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str


class AlertSender:
    """Envío de alertas ante errores críticos."""

    def __init__(self, config: AlertConfig):
        self.config = config

    async def check_and_alert(self, report: ReconciliationReport) -> None:
        critical = [d for d in report.discrepancies if d.severity == "CRITICAL"]

        if not critical:
            return

        subject = f"[SMARTBOTS ALERTA] {len(critical)} errores críticos - {report.run_id}"
        body = self._build_alert_body(report, critical)

        await self._send_email(subject, body)
        logger.critical(
            "critical_alert_sent",
            run_id=report.run_id,
            critical_count=len(critical),
        )

    def _build_alert_body(self, report, critical_discrepancies) -> str:
        lines = [
            f"Run ID: {report.run_id}",
            f"Timestamp: {report.timestamp.isoformat()}",
            f"Data Loss: {report.data_loss_pct:.2f}%",
            f"Amount Variance: ${report.amount_variance}",
            "",
            "--- Discrepancias Críticas ---",
        ]
        for d in critical_discrepancies:
            lines.extend([
                f"  Tipo: {d.type.value}",
                f"  Descripción: {d.description}",
                f"  Esperado: {d.expected}",
                f"  Actual: {d.actual}",
                "",
            ])
        return "\n".join(lines)
```

---

## 7. Roadmap Técnico por Fases

### Fase 1: Fundación (Semana 1)

**Entregables:**
- Estructura de directorios creada
- `pyproject.toml` con todas las dependencias
- Configuración de `ruff`, `mypy`, `pytest`
- `.env.example` + carga de configuración
- `Dockerfile` base con playwright-python
- Setup de logging estructurado
- CI básico (lint + type check)

**Riesgo:** Ninguno. Setup estándar.

### Fase 2: Dominio + API Discovery (Semana 2)

**Entregables:**
- Todas las entidades de dominio implementadas y testeadas
- Value objects (Money, Country) con validaciones
- Excepciones de dominio definidas
- 100% de unit tests del dominio passing
- Resultado de API Discovery con Taylor (iTrade)

**Riesgo:** API Discovery puede resultar en "no API disponible". **Mitigación:** El diseño ya contempla adapter pattern — si no hay API, se procede con Playwright sin impacto arquitectónico.

### Fase 3: Core ETL - Facturas (Semanas 3-4)

**Entregables:**
- Sistema de mapeo dinámico por transportista (YAML + loader)
- Validación Pydantic completa
- Estrategias de agrupación (por factura / por embarque)
- Reconciliation Report automático
- Tests de integración con archivos Excel reales
- Al menos 2 transportistas configurados

**Riesgo:** Formatos Excel inconsistentes entre transportistas. **Mitigación:** Mapeos YAML por carrier + validación Pydantic captura errores antes de procesar.

### Fase 4: RPA Playwright - POs (Semanas 5-7)

**Entregables:**
- Page Objects para todas las páginas de iTrade
- Flujo completo: Login → Extract PO → Confirm → Capture SO
- Parseo multi-item (1-a-N) funcional
- Idempotencia implementada (3 niveles)
- Manejo de errores con captura de screenshots/traces
- Session persistence (auth state)
- Escritura al Excel Maestro (1 fila por item)

**Riesgo:** Cambios en la UI de iTrade rompen selectores. **Mitigación:** Page Object Model aísla selectores en un solo archivo. Screenshots/traces facilitan debugging.

### Fase 5: Transición In Transit + Descarga PDFs (Semana 8)

**Entregables:**
- Flujo In Transit: ingreso peso/pallets/país CL
- Descarga de Confirmation of Sales PDF
- Tests con mocks del adaptador RPA

**Riesgo:** Rate-limiting de iTrade. **Mitigación:** Exponential backoff con jitter entre operaciones.

### Fase 6: Documentación Automática (Semana 9)

**Entregables:**
- Generador de 20 Pallet Tags por contenedor
- Generador de Planilla de Carga desde Orden de Embarque
- Templates Excel finalizados

**Riesgo:** Bajo. Templates ya existen, solo se automatiza el llenado.

### Fase 7: Weekly Report (Semana 10)

**Entregables:**
- Builder del reporte semanal para 10+ clientes
- Actualización de tablas dinámicas
- Envío automático por email (SMTP)
- Configuración de clientes en YAML

**Riesgo:** Complejidad de tablas dinámicas en openpyxl. **Mitigación:** Evaluar uso de xlsxwriter como alternativa para pivot tables.

### Fase 8: HITL + Integración Final (Semana 11)

**Entregables:**
- Flujo HITL para Invoice: datos preparados → estado "Pendiente de Revisión"
- Mecanismo de aprobación/rechazo humano
- Orquestador completo conectando todos los módulos
- Tests end-to-end con mocks

**Riesgo:** UX del flujo HITL no definida. **Mitigación:** Fase inicial usa archivos Excel marcados como "REVISAR" — evolución posterior a UI web si se requiere.

### Fase 9: Docker + Despliegue (Semana 12)

**Entregables:**
- `Dockerfile` optimizado con multi-stage build
- `docker-compose.yml` con volúmenes para datos
- Inyección de secretos via `.env`
- Alertas por email ante errores críticos
- Documentación de operación
- Runbooks para troubleshooting

**Riesgo:** Diferencias entre entorno local y Docker para Playwright. **Mitigación:** Imagen base `mcr.microsoft.com/playwright/python:v1.49.0-jammy`.

### Resumen de Riesgos Transversales

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|-------------|---------|-----------|
| iTrade UI changes | Alta | Alto | Page Object Model + screenshots + traces |
| No API disponible | Media | Bajo | Adapter pattern ya desacopla |
| Formatos Excel variables | Alta | Medio | YAML mapping + validación Pydantic |
| Data loss en ETL | Baja | Crítico | Reconciliation Report obligatorio + 0% loss validation |
| Rate-limiting iTrade | Media | Medio | Exponential backoff + session reuse |
| Errores en montos financieros | Baja | Crítico | Decimal (nunca float) + validación cruzada |

---

## Apéndice A: Dockerfile Base

```dockerfile
FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

WORKDIR /app

# Instalar uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copiar archivos de dependencias
COPY pyproject.toml uv.lock ./

# Instalar dependencias
RUN uv sync --frozen --no-dev

# Copiar código fuente
COPY src/ src/
COPY configs/ configs/
COPY templates/ templates/
COPY scripts/ scripts/

# Instalar browsers de Playwright
RUN uv run playwright install chromium

ENTRYPOINT ["uv", "run", "python"]
CMD ["scripts/run_po_cycle.py"]
```

## Apéndice B: Excepciones de Dominio

```python
# src/domain/exceptions.py
class SmartbotsError(Exception):
    """Base para todas las excepciones del ecosistema."""
    pass


class DomainValidationError(SmartbotsError):
    """Error de validación en reglas de negocio."""
    pass


class CountryCorrectionApplied(SmartbotsError):
    """Se aplicó corrección automática de país (NZ -> CL)."""
    def __init__(self, original: str, corrected: str, reason: str):
        self.original = original
        self.corrected = corrected
        self.reason = reason
        super().__init__(f"País corregido: {original} -> {corrected}. {reason}")


class POAlreadyProcessedError(SmartbotsError):
    """Intento de procesar una PO ya confirmada (idempotencia)."""
    pass


class ITradeConnectionError(SmartbotsError):
    """Error de conexión con iTrade."""
    pass


class ReconciliationFailedError(SmartbotsError):
    """El reporte de reconciliación detectó discrepancias críticas."""
    pass


class HITLReviewRequired(SmartbotsError):
    """Se requiere revisión humana antes de continuar."""
    pass
```
