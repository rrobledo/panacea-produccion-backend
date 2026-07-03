## ADDED Requirements

### Requirement: Insumos CRUD
The system SHALL provide `GET/POST /insumos` and
`GET/PUT/PATCH/DELETE /insumos/{id}` for the `Insumos` resource
(`codigo`, `nombre`, `unidad_medida`, `cantidad`, `precio`), matching the
reference backend's field set. `GET /insumos` SHALL support a `nombre`
query parameter that filters case-insensitively by substring and SHALL
order results by `nombre` ascending by default.

#### Scenario: List insumos filtered by name
- **WHEN** a client calls `GET /insumos?nombre=harina`
- **THEN** the response contains only insumos whose `nombre` contains
  "harina" (case-insensitive), ordered by `nombre`

#### Scenario: Create an insumo
- **WHEN** a client calls `POST /insumos` with a valid payload and a valid
  `X-API-Key` header
- **THEN** the system creates the row and returns 201 with the created
  resource including its generated `id`

### Requirement: Productos CRUD
The system SHALL provide `GET/POST /productos` and
`GET/PUT/PATCH/DELETE /productos/{id}` for the `Productos` resource
(`codigo`, `categoria`, `nombre`, `ref_id`, `utilidad`, `precio_actual`,
`unidad_medida`, `lote_produccion`, `tiempo_produccion`, `responsable`,
`categoria`, `habilitado`, `prioridad`, `is_producto`). `GET /productos`
SHALL support a `nombre` filter (case-insensitive substring) and SHALL
default-order by `prioridad` then `nombre` when no filter is applied.

#### Scenario: Create a product
- **WHEN** a client calls `POST /productos` with a valid payload and a
  valid `X-API-Key` header
- **THEN** the system creates the row and returns 201 with the created
  resource; the product is NOT automatically enrolled in planning or
  programacion as a side effect of creation

#### Scenario: Default product ordering
- **WHEN** a client calls `GET /productos` with no `nombre` filter
- **THEN** results are ordered by `prioridad` ascending, then `nombre`
  ascending

### Requirement: Producto cost detail (insumo composition)
The system SHALL provide `GET/POST /productos/{producto_id}/costos` and
`GET/PUT/PATCH/DELETE /productos/{producto_id}/costos/{id}` for the
`Costos` resource linking a producto to an insumo with a `cantidad`. List
responses SHALL include the linked insumo's `nombre` and `unidad_medida`
as read-only fields (`insumo_nombre`, `insumo_unidad_medida`).

#### Scenario: List a product's insumo detail
- **WHEN** a client calls `GET /productos/42/costos`
- **THEN** the response contains only cost-detail rows where
  `producto_id = 42`, each including `insumo_nombre` and
  `insumo_unidad_medida`

### Requirement: Product cost breakdown calculation
The system SHALL provide `GET /costos_materia_prima/{producto_id}`
returning a computed cost breakdown for the product: unit and per-lot cost
of materia prima, mano de obra, and fábrica; suggested price; margin;
monthly estimates; and a per-insumo cost detail list sorted by percentage
of total cost descending. The calculation SHALL accept optional
`cantidad_lotes`, `lote_produccion`, `utilidad`, and `precio_actual` query
parameters that override the product's stored values for that calculation
only (not persisted).

#### Scenario: Cost breakdown with stored values
- **WHEN** a client calls `GET /costos_materia_prima/42` with no override
  query params
- **THEN** the response uses product 42's stored `lote_produccion`,
  `utilidad`, and `precio_actual`, and includes `detalle_costo` sorted by
  `porcentaje_del_total` descending

#### Scenario: Cost breakdown with overrides
- **WHEN** a client calls `GET /costos_materia_prima/42?lote_produccion=200&utilidad=35`
- **THEN** the response computes costs using `lote_produccion=200` and
  `utilidad=35` instead of the product's stored values, without modifying
  the stored product

### Requirement: All-products cost summary
The system SHALL provide `GET /costos_materia_prima` returning the cost
breakdown summary (excluding the per-insumo detail list) for every product
whose `lote_produccion` is greater than 1, ordered by `producto_nombre`.

#### Scenario: List cost summaries
- **WHEN** a client calls `GET /costos_materia_prima`
- **THEN** the response includes one entry per product with
  `lote_produccion > 1`, each without a `detalle_costo` field, ordered by
  `producto_nombre`

### Requirement: Suggested price report
The system SHALL provide `GET /precio_productos` accepting an optional
`mes` query parameter (default: current month) and returning, per enabled
`is_producto=true` product, its reference prices (`precio_va`, `precio_cp`),
the current month's `corregido` plan value, and derived cost/margin/
suggested-price figures, ordered by `prioridad` then `producto_nombre`.

#### Scenario: Suggested price for current month
- **WHEN** a client calls `GET /precio_productos` with no `mes` parameter
- **THEN** the `plan` figure per product reflects the current calendar
  month's `corregido` value from planning

### Requirement: Static categories list
The system SHALL provide `GET /categorias` returning the fixed list of
cost categories used across the domain: "Materia Prima", "Honorarios",
"Servicios", "Mantenimiento", "Delivery", "Impuestos".

#### Scenario: Fetch categories
- **WHEN** a client calls `GET /categorias`
- **THEN** the response is the fixed 6-item list, in that order
