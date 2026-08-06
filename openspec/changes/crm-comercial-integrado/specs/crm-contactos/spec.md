## ADDED Requirements

### Requirement: Alta y edición de contacto
The system SHALL persist a `Contacto` entity representing a B2B or B2C
commercial contact, with a required `tipo` (`B2B` or `B2C`), basic contact
data (`nombre`, `email`, `telefono`), an optional link to an `Empresa`, an
optional link to an `Origen`, and an optional, nullable `erp_cliente_id`.

#### Scenario: Alta de contacto B2C sin vínculo ERP
- **WHEN** se crea un `Contacto` con `tipo="B2C"` y sin `erp_cliente_id`
- **THEN** el contacto queda persistido con `erp_cliente_id` nulo

#### Scenario: Alta de contacto B2B asociado a una empresa
- **WHEN** se crea un `Contacto` con `tipo="B2B"` y `empresa_id` de una
  `Empresa` existente
- **THEN** el contacto queda persistido con esa `Empresa` asociada

### Requirement: Contacto puede existir sin vínculo al ERP
The system SHALL allow a `Contacto` to exist and be fully usable (visitas,
oportunidades, campañas) without ever being linked to an `erp_cliente_id`.

#### Scenario: Contacto standalone participa en visitas y campañas
- **WHEN** un `Contacto` sin `erp_cliente_id` es asociado a una `Visita` o
  a una `Campaña`
- **THEN** la operación se completa sin requerir un vínculo ERP

#### Scenario: erp_cliente_id inexistente es rechazado
- **WHEN** se intenta crear o actualizar un `Contacto` con un
  `erp_cliente_id` que no corresponde a ninguna fila de `clientes`
- **THEN** el sistema rechaza la operación con un error de referencia
  inválida

### Requirement: Empresa como entidad propia
The system SHALL persist an `Empresa` entity independent of `Contacto`,
such that multiple contacts can belong to the same `Empresa`.

#### Scenario: Múltiples contactos en la misma empresa
- **WHEN** dos `Contacto` distintos se asocian a la misma `Empresa`
- **THEN** ambos aparecen al listar los contactos de esa `Empresa`

#### Scenario: Empresa sin contactos es válida
- **WHEN** se crea una `Empresa` sin ningún `Contacto` asociado todavía
- **THEN** la `Empresa` queda persistida y disponible para asociar
  contactos después

### Requirement: Catálogos de Rubro, Ciudad y Origen
The system SHALL persist `Rubro`, `Ciudad`, and `Origen` as catalog
entities that `Contacto`/`Empresa` reference by id.

#### Scenario: Contacto referencia catálogos existentes
- **WHEN** se crea un `Contacto` con `rubro_id`, `ciudad_id` u `origen_id`
  que existen
- **THEN** el contacto queda persistido con esas referencias

#### Scenario: Referencia a catálogo inexistente es rechazada
- **WHEN** se crea un `Contacto` con un `rubro_id`, `ciudad_id` u
  `origen_id` que no existe
- **THEN** el sistema rechaza la operación con un error de referencia
  inválida

### Requirement: Auditoría de cambios sobre contacto
The system SHALL record every create/update of a `Contacto` in an audit
log entry with the changed entity, field, previous value, new value,
acting user, and timestamp (RN-005).

#### Scenario: Edición de contacto queda auditada
- **WHEN** se actualiza un campo de un `Contacto` existente
- **THEN** se crea una entrada de auditoría con el valor anterior, el
  valor nuevo, el usuario que hizo el cambio y la fecha
