## ADDED Requirements

### Requirement: Vínculo manual de contacto a cliente ERP
The system SHALL allow linking an existing `Contacto` to an existing
`clientes` row by setting `erp_cliente_id`.

#### Scenario: Vincular contacto a cliente ERP existente
- **WHEN** se actualiza un `Contacto` con un `erp_cliente_id` que existe
  en `clientes`
- **THEN** el contacto queda vinculado a ese cliente ERP

#### Scenario: Vincular a cliente ERP inexistente es rechazado
- **WHEN** se intenta vincular un `Contacto` a un `erp_cliente_id` que no
  existe en `clientes`
- **THEN** el sistema rechaza la operación con un error de referencia
  inválida

### Requirement: Vínculo automático en la primera compra
The system SHALL automatically link a `Contacto` to its `erp_cliente_id`
when its first ERP purchase is detected, if it was not already linked.

#### Scenario: Primera compra vincula contacto sin ERP previo
- **WHEN** un `Contacto` sin `erp_cliente_id` corresponde (por otro medio
  de identificación, p.ej. CUIT/email coincidente) a un `clientes` que
  registra su primera compra en el ERP
- **THEN** el `Contacto` queda vinculado a ese `erp_cliente_id`

### Requirement: Historial de compras del contacto
The system SHALL expose, for a `Contacto` linked to `erp_cliente_id`, its
purchase history read directly from the ERP's purchase tables, without
duplicating that data into any CRM table.

#### Scenario: Consultar historial de compras de un contacto vinculado
- **WHEN** se consulta el historial de compras de un `Contacto` con
  `erp_cliente_id` vinculado
- **THEN** el sistema devuelve las compras de ese cliente leídas del ERP

#### Scenario: Contacto sin vínculo ERP no tiene historial de compras
- **WHEN** se consulta el historial de compras de un `Contacto` sin
  `erp_cliente_id`
- **THEN** el sistema devuelve una lista vacía, sin error

### Requirement: Productos más consumidos
The system SHALL expose, for a `Contacto` linked to `erp_cliente_id`, its
top purchased products by quantity or amount over a configurable period.

#### Scenario: Consultar productos más consumidos
- **WHEN** se consultan los productos más consumidos de un `Contacto`
  vinculado con compras registradas
- **THEN** el sistema devuelve los productos ordenados por consumo
  descendente

### Requirement: El CRM nunca escribe ventas en el ERP
The system SHALL NOT expose any CRM endpoint or service capable of
creating, updating, or deleting rows in the ERP's sales tables (`clientes`,
`panacea_sales_v2`) — the CRM only reads them. (Note: `panacea_sales_v2` is
the client-facing sales fact table, distinct from `compras_compra`, which
is this app's own supplier-purchasing ledger and unrelated to CRM
integration.)

#### Scenario: No existe endpoint de escritura de ventas en el CRM
- **WHEN** se inspeccionan los routers del módulo CRM
- **THEN** ninguno expone una operación de creación/edición/borrado sobre
  `clientes` o `panacea_sales_v2`
