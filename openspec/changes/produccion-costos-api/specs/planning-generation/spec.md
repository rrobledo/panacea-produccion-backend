## ADDED Requirements

### Requirement: Planning pivot read
The system SHALL provide `GET /planning` accepting an optional `anio` query
parameter (default: 2025, matching reference behavior unless overridden)
and returning, per enabled product, one row per year containing
`{YYYYMM}-PLAN`, `{YYYYMM}-SISTEMA`, `{YYYYMM}-CORREGIDO`, `{YYYYMM}-PROD`,
and `{YYYYMM}-VENTA` fields for each month with a planning row, plus a
synthetic `TOTAL` row summing all products per month.

#### Scenario: Fetch planning for a year
- **WHEN** a client calls `GET /planning?anio=2026`
- **THEN** the response includes one row per enabled product with
  monthly PLAN/SISTEMA/CORREGIDO/PROD/VENTA fields for 2026, plus a `TOTAL`
  summary row

### Requirement: Planning bulk cell edit
The system SHALL provide `POST /planning` accepting a list of per-product
edits (each keyed by product `id` and one or more `{YYYYMM}-{FIELD}` keys
for `PLAN`, `SISTEMA`, or `CORREGIDO`) and SHALL update only the specified
fields on the matching `producto_id` + `fecha` planning row, returning 204
on success. A blank string value SHALL be treated as `null`.

#### Scenario: Edit a single month's corrected plan
- **WHEN** a client calls `POST /planning` with
  `[{"id": 42, "202607-CORREGIDO": 150}]` and a valid `X-API-Key` header
- **THEN** the planning row for `producto_id=42`, `fecha=2026-07-01` has its
  `corregido` field set to 150 and other fields unchanged

### Requirement: Planning columns metadata
The system SHALL provide `GET /planning_columnas` accepting an optional
`anio` query parameter and returning a column-group structure (one group
per month present in that year's planning data) suitable for driving a
pivoted grid UI, matching the reference backend's structure.

#### Scenario: Fetch column metadata
- **WHEN** a client calls `GET /planning_columnas?anio=2026`
- **THEN** the response includes one column group per month that has at
  least one planning row for an enabled product in 2026

### Requirement: Annual planning generation
The system SHALL provide `POST /planning/generate` accepting `year`
(required or defaulted to the current year), an optional `producto_id`
(to scope generation to a single product instead of all enabled products),
and a `dry_run` flag that SHALL default to `true`. For each candidate
product, exactly one generation branch SHALL be selected based on whether
`panacea_sales_v2` has any rows for that product in `year - 1`.

#### Scenario: Scope to all enabled products
- **WHEN** a client calls `POST /planning/generate` with `year=2026` and no
  `producto_id`
- **THEN** every product with `habilitado = true` is a generation candidate

#### Scenario: Scope to a single product
- **WHEN** a client calls `POST /planning/generate` with `year=2026` and
  `producto_id=42`
- **THEN** only product 42 is a generation candidate, and the system
  rejects the request with 400 if product 42 is not `habilitado`

### Requirement: Zero-fill generation branch
The system SHALL, for a candidate product with no `panacea_sales_v2` rows
for `year - 1`, insert a planning row for every month 1-12 of `year` that
does not already have one, with `plan = 0`, `sistema = 0`, `indice = 0`.

#### Scenario: Product with no prior-year sales
- **WHEN** generating planning for `year=2026` for a product with zero
  `panacea_sales_v2` rows in 2025
- **THEN** the system inserts up to 12 rows for that product, one per month
  missing a planning row, each with `plan=0`, `sistema=0`, `indice=0`

### Requirement: Sales-projection generation branch
The system SHALL, for a candidate product with `panacea_sales_v2` rows for
`year - 1`, compute, per month, an index as the average across
`lugar_venta_id` groupings of (that place's that-month sales count ÷ that
place's average monthly sales count for `year - 1`, or 0 if the place's
average is 0), and SHALL insert a planning row with
`plan = sistema = ceil((product's overall average monthly sales × that
month's index) / 10) × 10` and `indice` = the rounded average index, for
every month missing a planning row. Months of `year - 1` with no sales data
for the product SHALL still receive a row for `year`, with
`plan = sistema = indice = 0` (zero-fill applied within the projection
branch for missing months, so every product ends up with exactly 12 rows).

#### Scenario: Product with full prior-year sales history
- **WHEN** generating planning for `year=2026` for a product with
  `panacea_sales_v2` rows in all 12 months of 2025
- **THEN** the system inserts up to 12 rows for `year=2026`, each `plan`
  value computed from that month's sales-index projection, rounded up to
  the nearest multiple of 10

#### Scenario: Product with partial prior-year sales history
- **WHEN** generating planning for `year=2026` for a product with
  `panacea_sales_v2` rows in only 8 of the 12 months of 2025
- **THEN** the system inserts a projection-based row for the 8 months with
  data and a zero-fill row (`plan=0`) for the 4 months without data — every
  product ends up with exactly 12 rows for the year

### Requirement: Idempotent, dry-run-capable generation
`POST /planning/generate` SHALL never insert a duplicate row for an
existing `(producto_id, fecha)` pair. When `dry_run=true` (the default), the
system SHALL compute and return the rows it would insert without writing to
the database. When `dry_run=false`, all inserts for the call SHALL commit
within a single transaction — a failure partway SHALL leave no partial
inserts from that call.

#### Scenario: Dry run does not write
- **WHEN** a client calls `POST /planning/generate` with `dry_run=true`
  (or omits `dry_run`)
- **THEN** the response lists the rows that would be inserted, and no rows
  are actually written to `costos_planificacion`

#### Scenario: Re-running generation is a no-op for existing rows
- **WHEN** `POST /planning/generate` is called twice in a row with
  `dry_run=false` for the same `year`
- **THEN** the second call inserts zero rows, since every `(producto_id,
  fecha)` pair from the first call already exists
