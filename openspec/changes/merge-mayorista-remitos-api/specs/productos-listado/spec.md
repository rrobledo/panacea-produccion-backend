## ADDED Requirements

### Requirement: Productos listing defaults to enabled-only
`GET /costos/productos` SHALL accept an optional `solo_habilitados` query
parameter (boolean, default `true`). When `true` (including when omitted),
the response SHALL exclude productos where `habilitado` is `false`. When
`false`, the response SHALL include productos regardless of `habilitado`.
This filter SHALL compose with the existing `nombre` filter and ordering.

#### Scenario: Default listing excludes disabled productos
- **WHEN** a caller requests `GET /costos/productos` with no
  `solo_habilitados` parameter, and the database has both enabled and
  disabled productos
- **THEN** the response includes only productos with `habilitado=true`

#### Scenario: Explicit opt-out includes disabled productos
- **WHEN** a caller requests `GET /costos/productos?solo_habilitados=false`
- **THEN** the response includes productos regardless of `habilitado`

#### Scenario: Filter composes with existing nombre search
- **WHEN** a caller requests `GET
  /costos/productos?nombre=pan&solo_habilitados=true`, and there exist both
  enabled and disabled productos whose nombre matches "pan"
- **THEN** the response includes only the enabled productos matching "pan"
