### Plan Técnico: Ecosistema de Automatización Loblo y Consolidación de Facturas

#### 1\. Análisis del requerimiento

El presente proyecto constituye un pilar crítico en la estrategia de transformación digital de la compañía, orientado a la eliminación de cuellos de botella operativos en la gestión de importaciones y logística. La transición de un modelo manual a un ecosistema automatizado de Purchase Orders (POs) y procesamiento de facturas no solo mitiga el riesgo de errores en datos sensibles (precios y cantidades), sino que garantiza la integridad de la cadena de pago. Al liberar al equipo de tareas repetitivas de baja escala, permitimos que la supervisión humana se centre en la validación estratégica y la gestión de excepciones, optimizando el  *lead time*  desde la confirmación de la orden hasta la habilitación del pago.

##### Objetivo del proyecto

Implementar un sistema robusto de RPA y ETL que gestione el ciclo de vida completo de las POs en iTrade (Confirmación, Tránsito, Facturación), automatice la descarga y organización documental, y centralice la facturación de transportistas en un maestro consolidado, incluyendo reportabilidad semanal para clientes.

##### Alcance funcional

* **Módulo Loblo/iTrade (RPA/API):**  
* **Investigación de API:**  Fase obligatoria de contacto con el ejecutivo de cuenta (Taylor) para priorizar integración vía API sobre Web Scraping.  
* **Gestión de Estados:**  Transición de POs a través de:  **Confirmed**  (extracción de SO y Loading Number),  **In Transit**  (ingreso mandatorio de: Peso, País de Origen "CL", Cantidad y Número de Pallets), e  **Invoice/Arrived** .  
* **Gestión Documental:**  Descarga de  *Confirmation of Sales*  (COS), renombrado sistemático a PO\_Number.pdf y almacenamiento en carpetas jerarquizadas por Loading Number.  
* **Módulo de Facturación (ETL):**  
* **Consolidación de Transportistas:**  Ingesta de archivos Excel de transportistas y carga en el "Consolidado de Facturas".  
* **Lógica de Agregación:**  Resolución de conflictos entre "una línea por factura" vs. "una línea por sub-orden/palet" según el formato del carrier.  
* **Módulo de Reportabilidad (Weekly Summary):**  
* Generación automática de resúmenes semanales para más de 10 clientes, filtrando el archivo maestro y enviando correos con el Excel adjunto.

##### Supuestos técnicos y Riesgos

Se asume la disponibilidad de credenciales para iTrade y acceso a las rutas de red/Drive. El riesgo crítico es la discrepancia de precios; se prescribe el uso de una bandera ( **"Pending Review"** ) en el Excel de control para validación humana contra el Programa Comercial antes de la facturación final.

#### 2\. Arquitectura propuesta

Como Arquitecto, prescribo una  **Arquitectura Modular con Separación de Responsabilidades** . Es imperativo que la lógica de navegación (Playwright/API) esté desacoplada de la lógica de transformación de datos (Pandas) y de la capa de reportabilidad. Esto permite un mantenimiento independiente y asegura que un cambio en la interfaz de iTrade no detenga el proceso de consolidación de facturas.

##### Flujo de datos conceptual

El sistema operará bajo un modelo de ingesta múltiple (Gmail, iTrade, Drive). Los datos serán normalizados mediante esquemas de validación antes de ser persistidos. Se utilizará  **SQLite**  como base de datos de estado para garantizar la  **idempotencia** , almacenando una clave compuesta de PO\_Number \+ Current\_State para evitar procesamientos duplicados.

##### Diagrama conceptual

\[ FUENTES \]              \[ MOTOR PYTHON \]               \[ DESTINOS \]  
\+-----------+          \+-----------------------+       \+-------------------+  
| iTrade    |--API/RPA |   CAPA DE INGESTA     |------\>| Portal iTrade     |  
| (Orders)  |          | (Validación Pydantic) |       | (Cambio Estados)  |  
\+-----------+          \+-----------+-----------+       \+-------------------+  
| Carrier   |          |           |           |       | Network Storage   |  
| Excels    |--Drive   |   ESTADO  | LOGICA DE |------\>| (PDFs PO\_Num.pdf) |  
\+-----------+          |  (SQLite) | NEGOCIO   |       \+-------------------+  
| Program   |          |           |           |       | Excel Consolidado |  
| Comercial |--Ref     \+-----------+-----------+------\>| (Maestro Facturas)|  
\+-----------+                                          \+-------------------+  
                                                       | Email (Clients)   |  
                                                       \+-------------------+

#### 3\. Stack Tecnológico

La estandarización es innegociable para controlar la deuda técnica.| Categoría | Herramienta | Justificación Técnica || \------ | \------ | \------ || **Lenguaje** | Python 3.12+ | Soporte para tipado estático y mejor rendimiento en manejo de hilos. || **Gestión** | **uv** | Velocidad superior en instalación de dependencias y aislamiento de entornos. || **Calidad** | **ruff** | Linter y formateador ultrarrápido para asegurar consistencia en el equipo. || **Automatización** | **Playwright** | Superior a Selenium; manejo nativo de contextos aislados y reintentos automáticos ante timeouts. || **Validación** | **Pydantic** | Creación de esquemas para normalizar datos (ej. conversión forzada de "NZ" a "CL"). || **Persistencia** | **SQLite / Pandas** | SQLite para control de estado e idempotencia; Pandas para ETL masivo. |

#### 4\. Árbol de directorios propuesto

La estructura debe soportar CI/CD y una clara separación de módulos de negocio.  
smartbots\_automation/  
├── src/  
│   ├── core/               \# Loggers, Database Manager (SQLite), Config  
│   ├── modules/  
│   │   ├── itrade/         \# API/Playwright Logic (States management)  
│   │   ├── invoices/       \# ETL Carrier consolidation logic  
│   │   └── reports/        \# Weekly summary email service  
│   ├── schemas/            \# Pydantic models (Data validation & normalization)  
│   └── services/           \# Gmail API & Drive integration  
├── data/  
│   ├── input/              \# Carrier Excels  
│   └── output/             \# Structured PDFs & Consolidated Master  
├── tests/                  \# Unitary & Integration (Mocked HTML)  
├── pyproject.toml          \# UV & Ruff configuration  
└── .env                    \# Secrets (Credentials, API Tokens)

#### 5\. Diseño del flujo ETL \+ RPA

##### Estrategia de Extracción y Transformación

1. **Normalización:**  El sistema debe detectar errores conocidos (ej. "NZ" en el portal) y normalizarlos a "CL" mediante el esquema Pydantic antes de cualquier inserción.  
2. **Mapeo de Identificadores:**  El Loading Number y el SO (Shipping Order) actuarán como Primary Keys para vincular los datos de iTrade con el consolidado de facturas.  
3. **Lógica Multi-ítem:**  Para POs con múltiples productos/pallets, el bot debe realizar una división de filas ( *row splitting* ) en el Excel de control, manteniendo los identificadores pero prorrateando cantidades.

##### Gestión Documental e Idempotencia

* **Descarga de COS:**  Al transicionar a "In Transit", el bot descargará el PDF, lo renombrará como PO\_Number.pdf y lo ubicará en /data/output/Loading\_Number/.  
* **Idempotencia:**  Antes de cada acción, el bot consultará SQLite. Si la tupla (PO, State) ya existe, se omite para evitar duplicidad de costos en iTrade.

##### Política de Reintentos

Dada la inestabilidad de las sesiones en iTrade, se define una política de  *Exponential Backoff*  en Playwright para manejar timeouts de sesión y errores 500 del servidor.

#### 6\. Plan de implementación por fases

1. **Fase 1 (Setup & API Research):**  Contacto con Taylor (iTrade) para factibilidad de API. Configuración de entorno con uv y ruff.  
2. **Fase 2 (Loblo RPA \- PO Logic):**  Desarrollo de navegación para confirmación de POs y extracción de SO/Loading. Implementación de descarga y renombrado de PDFs.  
3. **Fase 3 (In Transit Update):**  Módulo para actualizar estados ingresando Peso, COOL (CL), Qty y Pallets capturados desde los Excels de transportistas.  
4. **Fase 4 (Invoice ETL):**  Motor de consolidación con lógica de agregación de facturas y flag de "Pending Review".  
5. **Fase 5 (Client Reporting):**  Automatización del envío de Weekly Summaries a los 10+ clientes.

#### 7\. Estrategia de testing

* **Unit Testing:**  Validación rigurosa de las funciones de parsing de Excel y normalización de esquemas Pydantic.  
* **Integration Testing:**  Pruebas de flujo E2E desde la lectura del Excel de transportista hasta la simulación del cambio de estado en iTrade.  
* **RPA Mocking:**  Uso de  *Playwright Trace Viewer*  y archivos HTML estáticos para probar selectores de iTrade sin afectar datos reales de producción.

#### 8\. Estrategia de despliegue

* **CI/CD:**  Implementación de GitHub Actions para ejecución automática de ruff y pytest en cada commit.  
* **Configuración Segura:**  Todas las credenciales de iTrade, tokens de Gmail y rutas de red deben ser gestionadas estrictamente vía variables de entorno en archivos .env o Secretos de Repositorio.Este plan técnico asegura un sistema resiliente, escalable y con una trazabilidad absoluta, transformando la eficiencia operativa del departamento y garantizando la precisión en los pagos internacionales.

