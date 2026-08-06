## ADDED Requirements

### Requirement: Gestión de campañas
The system SHALL persist a `Campaña` entity with `nombre`, `fecha_inicio`,
`fecha_fin` (nullable, open-ended campaigns allowed), and an objective
description.

#### Scenario: Alta de campaña con fechas definidas
- **WHEN** se crea una `Campaña` con `fecha_inicio` y `fecha_fin`
- **THEN** la campaña queda persistida con ambas fechas

#### Scenario: Alta de campaña sin fecha de fin
- **WHEN** se crea una `Campaña` sin `fecha_fin`
- **THEN** la campaña queda persistida como abierta (`fecha_fin` nulo)

### Requirement: Asociación de contactos a campañas
The system SHALL allow a `Contacto` to be associated with any number of
`Campaña`, recording each association as `Contacto_Campaña` with the date
of association.

#### Scenario: Contacto asociado a múltiples campañas
- **WHEN** un mismo `Contacto` se asocia a dos `Campaña` distintas
- **THEN** ambas asociaciones quedan registradas de forma independiente

#### Scenario: Asociación duplicada es idempotente
- **WHEN** se intenta asociar el mismo `Contacto` a la misma `Campaña` una
  segunda vez
- **THEN** el sistema no crea una segunda fila `Contacto_Campaña`
  duplicada

### Requirement: Métricas base de conversión de campaña
The system SHALL expose, per `Campaña`, the count of associated contacts
and how many of those contacts have a non-null `erp_cliente_id`, as the
basis for the "campaña→registro" and "campaña→primera compra" conversion
KPIs.

#### Scenario: Conteo de contactos por campaña
- **WHEN** se consulta una `Campaña` con contactos asociados
- **THEN** el sistema devuelve la cantidad total de contactos asociados y
  la cantidad de esos contactos con `erp_cliente_id` no nulo
