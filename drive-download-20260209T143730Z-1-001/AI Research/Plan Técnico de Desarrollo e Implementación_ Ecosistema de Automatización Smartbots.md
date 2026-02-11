### Plan Técnico de Desarrollo e Implementación: Ecosistema de Automatización Smartbots

#### 1\. Análisis Técnico del Requerimiento

La operación actual de "Loblo" (iTrade) y la consolidación de facturas de transporte en Smartbots enfrenta un cuello de botella crítico debido a procesos manuales de alta densidad. La gestión de Purchase Orders (POs), la generación de etiquetas de pallets y el reporte semanal de embarques consumen jornadas completas, especialmente los domingos, introduciendo riesgos de errores en datos sensibles de precios y cantidades. Este plan propone la creación de un ecosistema de automatización modular que no solo elimine la carga operativa, sino que actúe como una capa de inteligencia de datos con validaciones rigurosas.

##### Objetivo y Alcance

* **Gestión RPA iTrade:**  Automatización del ciclo completo de POs (Confirmación, captura de SO, paso a "In Transit" con ingreso de pesos/pallets y descarga de PDFs de venta). Incluye la lógica de  **parseo 1-a-N**  para POs con múltiples ítems.  
* **Consolidación ETL de Facturas:**  Procesamiento de archivos Excel de transportistas con lógica de agrupación configurable (por factura o por embarque) y validación de esquemas.  
* **Generación de Documentación:**  Creación automática de  **Pallet Tags**  (20 etiquetas por contenedor) y  **Planillas de Carga**  basadas en la Orden de Embarque.  
* **Reporting Estratégico:**  Generación del "Weekly Ship Status" para más de 10 clientes cada domingo, automatizando la actualización de tablas dinámicas y envío de correos.

##### Requerimientos y Supuestos

* **No Funcionales:**  Trazabilidad total de acciones, idempotencia en la confirmación de POs, y un esquema de  **Human-in-the-Loop (HITL)**  para la fase de "Invoice" (pagos), dado su carácter delicado.  
* **Riesgos Técnicos y Mitigación:**  
* *Cambios en iTrade UI:*  Mitigado mediante el desacoplamiento en capas y una fase inicial de  **API Discovery**  para evaluar integración directa (contacto con ejecutivo Taylor).  
* *Datos Incorrectos (NZ vs CL):*  Implementación de reglas de negocio en la capa de dominio para corregir automáticamente códigos de país (ej. forzar "CL" sobre "NZ").  
* *Formatos Excel Variables:*  Uso de mapeos configurables por transportista para manejar discrepancias en nombres de columnas.

#### 2\. Arquitectura Propuesta

Para asegurar la escalabilidad, se adopta una  **Clean Architecture**  que separa las reglas de negocio (procesamiento de ítems, lógica de pallets) de los detalles de infraestructura (Scraping, APIs, Excel).

##### Modelo Arquitectónico

La estructura modular permite que el "Orquestador" invoque adaptadores específicos. Si se logra el acceso vía API para iTrade, solo se reemplazará el adaptador de infraestructura de Playwright por un cliente REST, manteniendo intacta la lógica de aplicación.

##### Componentes y Responsabilidades

Capa,Responsabilidad  
Domain,"Entidades (PO, Invoice, Pallet). Lógica de validación (NZ \-\> CL) y reglas de negocio puras."  
Application,"Casos de Uso: ""Confirmar Multi-item PO"", ""Generar Reporte Semanal"", ""Consolidar Facturas""."  
Infrastructure,"Gateways para Playwright (RPA), Pandas (ETL), Jinja2/ReportLab (Pallet Tags) y SMTP (Email)."

##### Diagrama de Arquitectura

graph TD  
    A\[Orquestador Principal\] \--\> B\[Módulo RPA iTrade / API Discovery\]  
    A \--\> C\[Módulo ETL Facturación\]  
    A \--\> D\[Módulo Documental \- Pallet Tags\]  
    A \--\> E\[Módulo Reporting \- Weekly Status\]

    subgraph "Infrastructure (Adapters)"  
    B \--\> B1\[Playwright / REST Client\]  
    C \--\> C1\[Pandas \- Configurable Mapper\]  
    D \--\> D1\[Template Engine \- Excel/PDF\]  
    E \--\> E1\[SMTP Server / Pivot Update\]  
    end

    subgraph "Domain & Application"  
    B1 \--\> F\[Lógica 1-N PO Items\]  
    C1 \--\> G\[Reglas de Agrupación de Facturas\]  
    end

    F \--\> H\[(Reconciliation Report)\]  
    G \--\> H

#### 3\. Stack Tecnológico y Justificación

* **Python \+ uv:**  Se utilizará uv por su superioridad en la gestión de dependencias y velocidad de ejecución, asegurando entornos deterministas en segundos.  
* **Playwright:**  Preferido sobre Selenium por su resiliencia ante sitios dinámicos, manejo nativo de esperas y capacidad de capturar trazas de video/screenshots ante fallos en iTrade.  
* **Pandas & Pydantic:**  Pandas para la manipulación de datos masivos y Pydantic para la validación estricta de los datos de entrada (precios, cantidades, pesos).  
* **Ruff:**  Herramienta de linting y formateo para mantener un estándar de código senior (PEP8) y prevenir bugs latentes.

#### 4\. Árbol de Directorios Propuesto

smartbots-ecosystem/  
├── pyproject.toml        \# Configuración de uv y ruff  
├── .env                  \# Credenciales (iTrade, SMTP, Rutas Drive)  
├── templates/            \# Plantillas Excel (Master, Pallet Tags, Weekly Summary)  
├── src/  
│   ├── domain/           \# Entidades (POItem, Shipment, Invoice)  
│   ├── application/      \# Casos de uso (process\_po.py, consolidate\_invoices.py)  
│   ├── infrastructure/     
│   │   ├── adapters/     \# itrade\_api\_client.py, excel\_handler.py  
│   │   └── rpa/          \# playwright\_scrapers.py  
│   ├── reports/          \# Módulo de Reporte Semanal (Sundays)  
│   └── document\_gen/     \# Generador de Pallet Tags y Planillas de Carga  
├── tests/                \# Unitarias (Mocks de POs) e Integración  
├── logs/                 \# Trazabilidad y Reconciliation Reports  
└── configs/              \# Mapeos de transportistas y reglas NZ-\>CL

#### 5\. Diseño del Flujo ETL \+ RPA

##### RPA iTrade: Lógica Multi-Item y Estado "In Transit"

El bot debe manejar POs que contienen múltiples ítems (ej. Grapes Green, PC Black).

1. **Iteración:**  Por cada PO, extraer tabla de ítems.  
2. **Mapeo 1-a-N:**  Crear una fila en el Excel Maestro por cada ítem de la PO.  
3. **Actualización:**  Al pasar a "In Transit", el bot debe extraer Peso Total, Pallet Count y Cajas desde la Planilla de Carga e ingresarlos en iTrade, forzando el país como "CL".

##### ETL Facturas: Consolidación Configurable

El sistema leerá los Excel de transportistas y, según configuración, agrupará los datos:

* **Opción A:**  Una línea por factura (Totalizando ítems).  
* **Opción B:**  Una línea por embarque/guía.

##### Diagramas de Flujo

**Flujo de Gestión de POs (1-a-N)**  
flowchart TD  
    A\[Inicio\] \--\> B\[Login iTrade\]  
    B \--\> C{¿Existen POs?}  
    C \-- Sí \--\> D\[Extraer PO Data\]  
    D \--\> E\[Iterar Ítems de la PO\]  
    E \--\> F\[Actualizar Maestro \- 1 fila por Ítem\]  
    F \--\> G\[Confirmar PO y Capturar SO\]  
    G \--\> H\[Cambiar a In Transit \- Ingresar Peso/Pallets/CL\]  
    H \--\> I\[Descargar Confirmation of Sales PDF\]  
    I \--\> C  
    C \-- No \--\> J\[Generar Reconciliation Report\]

**Proceso de Generación de Etiquetas y Carga**  
flowchart LR  
    A\[Orden de Embarque\] \--\> B\[Identificar 20 Pallets\]  
    B \--\> C\[Extraer Datos del Maestro\]  
    C \--\> D\[Generar 20 Pallet Tags PDF\]  
    D \--\> E\[Llenar Planilla de Carga\]

#### 6\. Workflow de Desarrollo

1. **Fase 1: Inicialización:**  Configuración de uv, ruff y estructura de directorios.  
2. **Fase 2: API Discovery:**  Investigación de factibilidad técnica de la API de iTrade (Taylor).  
3. **Fase 3: Modelado de Dominio:**  Definición de esquemas Pydantic (Validación NZ-\>CL).  
4. **Fase 4: Core ETL:**  Implementación del consolidador de facturas con lógica de agrupación.  
5. **Fase 5: RPA Playwright:**  Desarrollo del bot de navegación (Confirmación y Descarga).  
6. **Fase 6: Reporting:**  Automatización del "Weekly Ship Status" (Sunday Report).  
7. **Fase 7: Documentación:**  Módulo de generación de Pallet Tags y Planillas de Carga.  
8. **Fase 8: Testing & QA:**  Pruebas con Mocks de iTrade y validación de datos financieros.  
9. **Fase 9: Despliegue & HITL:**  Setup en Docker y configuración de revisión manual para fase de "Invoice".

#### 7\. Estrategia de Testing

* **Unitarias:**  Validación de la lógica de transformación (ej. asegurar que el cálculo de pesos coincida entre Maestro y Planilla de Carga).  
* **Integración:**  Pruebas de lectura/escritura en red y Google Drive.  
* **RPA Testing:**  Uso de  **Mocks para los objetos de respuesta de iTrade** , permitiendo probar la lógica de parseo Multi-item sin realizar clics reales.  
* **Reconciliation:**  El bot debe comparar lo extraído vs lo guardado para garantizar que no hay pérdida de información (0% data loss goal).

#### 8\. Estrategia de Despliegue

* **Contenerización:**  Uso de  **Docker**  (Imagen playwright-python) para evitar discrepancias de drivers entre entornos.  
* **Secretos:**  Gestión de credenciales mediante .env inyectado en tiempo de ejecución.  
* **Monitoreo:**  Sistema de alertas vía Email/Logs que informe el éxito o error de cada PO procesada.

#### 9\. Buenas Prácticas y Consideraciones

* **Human-in-the-Loop (HITL):**  Dada la sensibilidad financiera en la etapa de facturación (Invoice), el bot preparará los datos y los dejará en un estado "Pendiente de Revisión" para que un humano valide precios finales antes del envío a pago.  
* **Observabilidad:**  Generación obligatoria del  **Reconciliation Report**  al finalizar cada ejecución.  
* **Resiliencia Web:**  Implementación de esperas inteligentes (Smart Waits) y manejo de sesiones para evitar bloqueos por rate-limiting en iTrade.Este plan técnico transforma los procesos de Smartbots en un ecosistema robusto, auditable y escalable, garantizando la integridad de la data desde el origen en iTrade hasta el reporte final al cliente.

