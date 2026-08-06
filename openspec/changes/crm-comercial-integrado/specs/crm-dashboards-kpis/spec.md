## ADDED Requirements

### Requirement: Dashboard ejecutivo
The system SHALL expose an executive dashboard endpoint aggregating
company-wide commercial KPIs (conversion rates, CAC, CLV, sales by
segment/city/vendor) over a selectable date range.

#### Scenario: Consultar dashboard ejecutivo
- **WHEN** un usuario con rol autorizado (Administrador o Gerencia)
  consulta el dashboard ejecutivo para un rango de fechas
- **THEN** el sistema devuelve los KPIs agregados para ese rango

### Requirement: Dashboard de vendedor
The system SHALL expose a per-vendor dashboard endpoint showing that
vendor's pipeline (opportunities by stage), visits, and assigned
contacts.

#### Scenario: Vendedor consulta su propio dashboard
- **WHEN** un usuario con rol `vendedor` consulta su dashboard
- **THEN** el sistema devuelve únicamente el pipeline, visitas y
  contactos asignados a ese vendedor

#### Scenario: Vendedor no puede consultar el dashboard de otro vendedor
- **WHEN** un usuario con rol `vendedor` intenta consultar el dashboard
  de otro vendedor
- **THEN** el sistema responde con 403 forbidden

### Requirement: Dashboard de marketing
The system SHALL expose a marketing dashboard endpoint showing campaign
performance (conversion campaña→registro→primera compra, ROI por
campaña) and segment composition.

#### Scenario: Consultar dashboard de marketing
- **WHEN** un usuario con rol autorizado (Marketing, Gerencia o
  Administrador) consulta el dashboard de marketing
- **THEN** el sistema devuelve las métricas de campañas y segmentos

### Requirement: KPIs de conversión y campaña
The system SHALL compute conversión visitas→clientes, conversión
campaña→registro, conversión registro→primera compra, and ROI por
campaña.

#### Scenario: Calcular conversión visitas→clientes
- **WHEN** se solicita el KPI de conversión visitas→clientes para un
  rango de fechas con visitas y compras registradas
- **THEN** el sistema devuelve el porcentaje de contactos visitados que
  llegaron a tener al menos una compra ERP

### Requirement: KPIs de valor de cliente
The system SHALL compute CAC (costo de adquisición de cliente), CLV
(valor de vida del cliente), ticket promedio, frecuencia de compra, and
fecha de última compra, derived from ERP purchase data joined by
`erp_cliente_id`.

#### Scenario: Calcular CLV de un contacto vinculado
- **WHEN** se solicita el CLV de un `Contacto` con `erp_cliente_id`
  vinculado y compras registradas
- **THEN** el sistema devuelve el valor acumulado de compras de ese
  cliente en el ERP

### Requirement: Clientes inactivos y alertas
The system SHALL identify contacts whose last ERP purchase is older than
a configurable threshold as inactivos, expose them in a list, and mark
contacts that resume purchasing after being inactive as recuperados.

#### Scenario: Listar clientes inactivos
- **WHEN** se consulta la lista de clientes inactivos con el umbral
  configurado
- **THEN** el sistema devuelve los contactos vinculados a ERP cuya última
  compra supera ese umbral

#### Scenario: Cliente recuperado tras nueva compra
- **WHEN** un `Contacto` marcado como inactivo registra una nueva compra
  ERP
- **THEN** el sistema lo excluye de la lista de inactivos y lo cuenta
  como recuperado

### Requirement: Ventas por segmento, ciudad y vendedor
The system SHALL expose sales aggregated by `Segmento`, `Ciudad`, and
`Vendedor`, joining ERP purchase data through `erp_cliente_id`.

#### Scenario: Consultar ventas por ciudad
- **WHEN** se solicita el KPI de ventas por ciudad para un rango de
  fechas
- **THEN** el sistema devuelve el total vendido agrupado por `Ciudad` de
  los contactos vinculados

### Requirement: Exportación de reportes
The system SHALL allow exporting any KPI/dashboard result set as CSV.

#### Scenario: Exportar reporte de ventas por segmento
- **WHEN** un usuario con rol autorizado solicita la exportación de
  ventas por segmento
- **THEN** el sistema devuelve un archivo CSV con esos datos

### Requirement: Dashboard 360° de cliente
The system SHALL expose, per `Contacto`, a combined read-model with:
datos generales, origen, fecha de registro, campañas asociadas, últimas
visitas, pipeline (oportunidades), últimas compras (ERP), productos
favoritos (ERP), facturación de los últimos 12 meses (ERP), frecuencia de
compra, próxima acción (siguiente actividad pendiente), y observaciones.

#### Scenario: Consultar dashboard 360° de un contacto vinculado a ERP
- **WHEN** se consulta el dashboard de un `Contacto` con `erp_cliente_id`
  vinculado, campañas, visitas y oportunidades registradas
- **THEN** el sistema devuelve todos los bloques definidos, combinando
  datos del CRM y del ERP

#### Scenario: Consultar dashboard 360° de un contacto sin ERP
- **WHEN** se consulta el dashboard de un `Contacto` sin `erp_cliente_id`
- **THEN** el sistema devuelve los bloques del CRM completos y los
  bloques dependientes del ERP (compras, productos favoritos,
  facturación) vacíos, sin error
