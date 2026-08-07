## ADDED Requirements

### Requirement: Definición de segmento
The system SHALL persist a `Segmento` entity with a `nombre` and a
`criterio` (a structured filter definition over contact and purchase
attributes — e.g. ciudad, rubro, frecuencia de compra, inactividad).

#### Scenario: Alta de segmento con criterio
- **WHEN** se crea un `Segmento` con `nombre` y `criterio` válidos
- **THEN** el segmento queda persistido, todavía sin contactos asignados

### Requirement: Recalculo de pertenencia a segmentos
The system SHALL recompute `Contacto_Segmento` membership by evaluating
each `Segmento.criterio` against current contact/purchase data, via a
recurring internal job.

#### Scenario: Recompute agrega contactos que cumplen el criterio
- **WHEN** corre el job de recompute y un `Contacto` pasa a cumplir el
  `criterio` de un `Segmento` al que no pertenecía
- **THEN** se crea la fila `Contacto_Segmento` correspondiente con su
  timestamp de recálculo

#### Scenario: Recompute remueve contactos que dejan de cumplir el criterio
- **WHEN** corre el job de recompute y un `Contacto` que pertenecía a un
  `Segmento` deja de cumplir su `criterio`
- **THEN** la fila `Contacto_Segmento` correspondiente se elimina

### Requirement: Recompute manual bajo demanda
The system SHALL expose an authenticated endpoint that triggers an
immediate recompute of segment membership, independent of the scheduled
job.

#### Scenario: Recompute manual con sesión autenticada
- **WHEN** un usuario autenticado (cualquier rol — el endpoint ya no exige
  un rol comercial específico, ver `role-authorization`) invoca el
  endpoint de recompute manual
- **THEN** el sistema recalcula `Contacto_Segmento` para todos los
  `Segmento` y actualiza su timestamp de recálculo

#### Scenario: Recompute manual sin sesión
- **WHEN** un usuario sin token de autenticación válido invoca el
  endpoint de recompute manual
- **THEN** el sistema responde con 401 unauthorized y no recalcula nada
