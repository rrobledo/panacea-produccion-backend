## ADDED Requirements

### Requirement: Pipeline de oportunidades sobre etapas
The system SHALL persist an `Oportunidad` entity associated with a
`Contacto` and currently positioned on one `Etapa_Venta` from a fixed,
ordered set of stages (Lead, Visita, Interesado, Muestras, Presupuesto,
Negociación, Primera Compra, Cliente Activo).

#### Scenario: Alta de oportunidad en etapa inicial
- **WHEN** se crea una `Oportunidad` para un `Contacto`
- **THEN** queda persistida en la etapa `Lead` por defecto

#### Scenario: Cambio de etapa de una oportunidad
- **WHEN** se actualiza la `Etapa_Venta` de una `Oportunidad` existente a
  una etapa válida
- **THEN** la oportunidad queda persistida en la nueva etapa y se
  conserva el historial de la transición

### Requirement: Actividades asociadas a una oportunidad
The system SHALL persist an `Actividad` entity linked to an `Oportunidad`,
with `tipo`, `fecha`, and `notas`.

#### Scenario: Registrar actividad ligada a una oportunidad
- **WHEN** se crea una `Actividad` con `oportunidad_id` válido
- **THEN** la actividad queda persistida asociada a esa oportunidad

#### Scenario: Listar actividades de una oportunidad
- **WHEN** se consultan las actividades de una `Oportunidad` con varias
  actividades registradas
- **THEN** el sistema las devuelve ordenadas por `fecha`

### Requirement: Oportunidad ganada se vincula a la primera compra ERP
The system SHALL allow marking an `Oportunidad` as ganada (etapa
`Primera Compra` o posterior) only once its `Contacto` has a non-null
`erp_cliente_id` with at least one purchase recorded in the ERP.

#### Scenario: Oportunidad marcada como ganada tras primera compra
- **WHEN** el `Contacto` de una `Oportunidad` obtiene su primera compra
  ERP (queda con `erp_cliente_id` vinculado y al menos una compra)
- **THEN** la `Oportunidad` puede avanzar a la etapa `Primera Compra`

#### Scenario: No se puede marcar como ganada sin compra ERP
- **WHEN** se intenta avanzar una `Oportunidad` a la etapa
  `Primera Compra` para un `Contacto` sin `erp_cliente_id` vinculado
- **THEN** el sistema rechaza la transición de etapa

### Requirement: Auditoría de cambios sobre oportunidad y actividad
The system SHALL record every create/update of an `Oportunidad` (including
stage changes) and every create of an `Actividad` in an audit log entry
with the changed entity, field, previous value, new value, acting user,
and timestamp (RN-005).

#### Scenario: Cambio de etapa queda auditado
- **WHEN** se cambia la `Etapa_Venta` de una `Oportunidad`
- **THEN** se crea una entrada de auditoría con la etapa anterior, la
  etapa nueva, el usuario que hizo el cambio y la fecha
