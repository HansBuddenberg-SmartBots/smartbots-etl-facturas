### Briefing: Proyecto de Automatización de Procesos Smartbots

#### Resumen Ejecutivo

Este documento sintetiza las necesidades y oportunidades de automatización identificadas en los procesos operativos de gestión de órdenes de compra (PO) y consolidación de facturas. El análisis revela una dependencia crítica de tareas manuales repetitivas que consumen un tiempo considerable, especialmente en la interacción con la plataforma  **iTrade**  y el manejo de planillas Excel.Los puntos clave identificados son:

* **Proceso Loblo (iTrade):**  Es el principal receptor de tiempo debido a múltiples etapas manuales que van desde la confirmación de PO hasta el seguimiento de tránsito y facturación.  
* **Gestión de Carga:**  La creación de planillas de carga y etiquetas de pallets presenta una alta complejidad lógica pero es automatizable si se estructuran correctamente los datos de origen.  
* **Consolidación de Facturas:**  Existe un flujo de trabajo de tipo ETL (Extracción, Transformación y Carga) para unificar la información de transportistas en un control centralizado, actualmente realizado de forma manual.  
* **Estrategia Técnica:**  Se evalúa la transición de automatizaciones basadas en interfaz de usuario hacia integraciones mediante  **API**  para mayor velocidad y seguridad, utilizando lenguajes como Python para el procesamiento de datos.

#### 1\. Gestión de Órdenes de Compra (PO) y Sistema iTrade

El proceso de gestión de PO para el cliente "Loblo" es el flujo más intensivo en términos de horas hombre. Se divide en varias etapas temporales no secuenciales que dependen del ciclo de vida de la mercadería.

##### Flujo de Trabajo en iTrade

El sistema iTrade es una plataforma externa donde se gestionan las órdenes. El flujo actual comprende:| Etapa | Descripción de la Tarea Manual | Datos Relevantes || \------ | \------ | \------ || **Recepción y Confirmación** | Se reciben avisos por correo. Se debe ingresar a iTrade, buscar las PO y confirmarlas una por una. | Número de PO, Loading Number, SKU/Item. || **Extracción de Datos** | Una vez confirmada la PO, se genera el número de  **SO**  (Sales Order), el cual debe copiarse manualmente a un Excel maestro. | SO, precio, cantidad de cajas, DC (Centro de Distribución). || **Cambio a "In Transit"** | Tras el zarpe del barco, se debe actualizar el estado de cada PO a "In Transit" e ingresar datos de peso y origen. | Peso total, País de origen (Chile), número de pallets. || **Descarga de Documentos** | Descarga de "Confirmation of Sales" (COs) en formato PDF, renombrándolos y organizándolos en carpetas por Loading Number. | PDF de la PO, Nombre de carpeta según Loading Number. || **Facturación (Invoicing)** | Revisión final de cantidades y precios contra la planilla maestra antes de pasar al estado de pago. | Monto total, validación de ítems. |  
**Cita clave:**  "Loblo es el principal recibidor que ocupa más tiempo en la temporada porque tiene un montón de pasos manuales que hay que hacer."

#### 2\. Documentación de Operaciones y Reportes de Embarque

Más allá del sistema iTrade, el equipo de operaciones realiza tareas de síntesis de información para la logística y el servicio al cliente.

##### Planilla de Carga y Etiquetas (Palet Tags)

Este proceso vincula las PO con la realidad física del contenedor:

* **Lógica de Distribución:**  Un contenedor estándar transporta 20 pallets. El desafío radica en que una sola PO puede contener múltiples ítems (ej. uvas de distintos colores) que deben distribuirse en una cantidad específica de pallets.  
* **Automatización Propuesta:**  Utilizar la información del Excel maestro para pre-llenar la planilla de carga, evitando que el usuario deba calcular manualmente cuántos pallets corresponden a cada ítem de la PO.

##### Reporte Semanal de Estatus (Ship Status)

Cada domingo, se genera un resumen para los clientes sobre las cargas de la semana:

* **Proceso Actual:**  Se filtra un "Maestro de Embarque" por cliente, se copia la data en un Excel específico con tablas dinámicas y se envía por correo.  
* **Frecuencia:**  Semanal (domingos), abarcando aproximadamente 10 clientes.  
* **Formato:**  Se prefiere el envío de archivos Excel debido a que los clientes necesitan aplicar filtros propios.

#### 3\. Consolidación de Facturas de Transporte

El área de operaciones maneja un flujo crítico de validación de costos de transporte. Los transportistas envían facturas escaneadas, guías de despacho y, obligatoriamente, un  **detalle en Excel** .

##### El Proceso de Consolidación (ETL)

El objetivo es traspasar la información de los diversos Excel de los transportistas a un  **"Consolidado de Facturas"**  (Base de Datos interna en Excel).

* **Entradas:**  Archivos Excel de transportistas con formato estandarizado.  
* **Transformación:**  El bot debe rescatar columnas específicas (N° Factura, Fecha, Orden de Embarque, Totales) y mapearlas en el archivo centralizador.  
* **Validación:**  Previo a la ejecución del bot, un operador revisa que la factura sea correcta. El bot actúa sobre archivos ya validados depositados en una carpeta específica (ej. Google Drive).  
* **Frecuencia:**  Ejecución diaria o cada 2-3 días para evitar retrasos en los procesos de pago de finanzas.

#### 4\. Análisis Técnico y Factibilidad

El análisis de las fuentes sugiere un enfoque híbrido para la implementación de estas soluciones.

##### Estrategias de Implementación

1. **Uso de APIs:**  Se identifica que iTrade es una plataforma de terceros. La comunicación directa mediante API se prefiere sobre el  *web scraping*  tradicional por ser "mucho más rápido y seguro".  
2. **Procesamiento con Python:**  Para la consolidación de facturas, se propone el uso de Python para realizar la extracción y carga de datos entre planillas Excel, dada la baja complejidad técnica y la alta repetibilidad del proceso.  
3. **Estructura de Datos:**  Se requiere un mapeo preciso de columnas (ej. asegurar que la columna "Conductor" en el origen corresponda a la columna correcta en el destino) para garantizar la integridad de la base de datos central.

##### Cronograma y Valorización Estimada

Para procesos de complejidad baja-media, como la consolidación de facturas de transporte:

* **Tiempo de Desarrollo:**  Estimado en 15 días hábiles (con posibilidad de entrega anticipada en 10 días para generar una percepción de alta eficiencia).  
* **Complejidad:**  Considerada "baja" en términos de lógica de programación, pero con alto valor operativo.**Observación técnica:**  "Esto es un traspaso de información de Excel a Excel... lo podemos hacer perfectamente en Python. La complejidad es bajísima."

