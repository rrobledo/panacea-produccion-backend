## ADDED Requirements

### Requirement: Clientes CRUD
The system SHALL provide `GET/POST /clientes` and
`GET/PUT/PATCH/DELETE /clientes/{id}` for the `Clientes` resource, exposing
a computed `nombre` field (`"{nom1}, {nom2}"`). `GET /clientes` SHALL
support a `nombre` filter matching case-insensitively against either
`nom1` or `nom2`, and SHALL order results by `nom1` by default.

#### Scenario: Filter clientes by name
- **WHEN** a client calls `GET /clientes?nombre=garcia`
- **THEN** the response includes clientes where `nom1` or `nom2` contains
  "garcia" (case-insensitive)

### Requirement: Remitos CRUD with nested delivery detail
The system SHALL provide `GET/POST /remitos` and
`GET/PUT/PATCH/DELETE /remitos/{id}` for the `Remitos` resource, with a
nested `productos` list of delivery detail lines (`producto`, `cantidad`,
`entregado`, `observaciones`), created together with the parent remito in a
single request. Detail lines with `cantidad <= 0` SHALL be silently
excluded from creation. `GET /remitos` SHALL support `cliente` (name
substring) and `estado` filters, and SHALL order results by
`fecha_entrega` by default.

#### Scenario: Create a remito with detail lines
- **WHEN** a client calls `POST /remitos` with a `productos` array
  containing two lines, one with `cantidad=5` and one with `cantidad=0`
- **THEN** the remito is created with only the `cantidad=5` line persisted

#### Scenario: Computed estado field
The system SHALL compute a remito's `estado` field from its timestamp
fields: `"ENTREGADO"` if `fecha_recibido` is set, else `"EN CAMINO"` if
`fecha_despacho` is set, else `"PREPARADO"` if `fecha_listo` is set, else
`"EN_PREPARACION"` if `fecha_preparacion` is set, else `"PENDIENTE"`.
- **WHEN** a remito has `fecha_despacho` set but not `fecha_recibido`
- **THEN** its `estado` field is `"EN CAMINO"`

#### Scenario: Filter remitos by estado
- **WHEN** a client calls `GET /remitos?estado=PENDIENTE`
- **THEN** only remitos whose computed `estado` is `"PENDIENTE"` are
  returned; `estado=ALL` (or omitted) returns all remitos regardless of
  computed state
