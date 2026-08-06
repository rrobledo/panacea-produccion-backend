## ADDED Requirements

### Requirement: Vínculo de contacto a socio del Club
The system SHALL allow linking a `Contacto` to a Club de Socios member id,
and SHALL persist the last known member state (`categoria`, `puntos`,
`fecha_alta`) in a local `Club_Socio` cache row.

#### Scenario: Contacto vinculado expone su estado de socio
- **WHEN** se consulta un `Contacto` vinculado a un socio del Club con
  cache poblada
- **THEN** el sistema devuelve `categoria`, `puntos` y `fecha_alta` desde
  la cache local

#### Scenario: Contacto sin vínculo al Club no tiene estado de socio
- **WHEN** se consulta un `Contacto` sin vínculo al Club
- **THEN** el sistema devuelve el estado de socio como ausente, sin error

### Requirement: La cache local se refresca por proceso batch
The system SHALL refresh the `Club_Socio` cache via a recurring internal
job that calls the external Club de Socios API, and SHALL NOT call that
external API synchronously in the request path of a user-facing read.

#### Scenario: Consulta de dashboard usa cache aunque el Club esté caído
- **WHEN** se consulta el estado de socio de un `Contacto` mientras la
  API externa del Club de Socios no responde
- **THEN** el sistema devuelve el último estado cacheado, sin fallar la
  consulta

#### Scenario: Refresco por cron actualiza la cache
- **WHEN** corre el job de refresco y la API del Club de Socios devuelve
  una `categoria`/`puntos` distinta a la cacheada para un socio
- **THEN** la cache local se actualiza con los valores nuevos y su
  timestamp de refresco
