## ADDED Requirements

### Requirement: Production report by category
The system SHALL provide `GET /get_produccion_by_category` accepting
`anio` and `mes` query parameters and returning, per product `categoria`
with a positive total plan for that month, the summed planned quantity,
produced quantity, sold quantity, and the percentage of plan executed and
percentage of plan sold.

#### Scenario: Fetch category report
- **WHEN** a client calls `GET /get_produccion_by_category?anio=2026&mes=7`
- **THEN** the response includes one row per category with `plan > 0` for
  July 2026, each with `planeado`, `producido`, `vendido`,
  `porcentaje_ejecutado`, and `porcentaje_vendido`

### Requirement: Production report by product
The system SHALL provide `GET /get_produccion_by_productos` accepting
`anio` and `mes` query parameters and returning the same metrics as the
category report, broken out per product (joined against reference-code
mapping data) instead of per category.

#### Scenario: Fetch product-level report
- **WHEN** a client calls `GET /get_produccion_by_productos?anio=2026&mes=7`
- **THEN** the response includes one row per product (with a resolvable
  reference code) with `planeado`, `producido`, `vendido`, and the two
  percentage metrics for July 2026

### Requirement: Insumos usage by period
The system SHALL provide `GET /get_insumos_by_month` accepting `anio`,
`mes`, optional `semana`, and a `by_week` flag (`yes`/`no`) and returning,
per insumo, the planned and actually-used quantity and cost for the
selected period — grouped by week within the month when `by_week=yes`
(the default), or by month when `by_week=no` — plus a `Total` row summing
planned and used cost across all insumos.

#### Scenario: Weekly insumo usage
- **WHEN** a client calls
  `GET /get_insumos_by_month?anio=2026&mes=7&by_week=yes&semana=2`
- **THEN** the response includes per-insumo planned/used quantity and cost
  for week 2 of July 2026 only, plus a `Total` row

#### Scenario: Monthly insumo usage
- **WHEN** a client calls `GET /get_insumos_by_month?anio=2026&mes=7&by_week=no`
- **THEN** the response includes per-insumo planned/used quantity and cost
  aggregated across all of July 2026, plus a `Total` row

### Requirement: Sales by client report
The system SHALL provide `GET /get_ventas_por_cliente` accepting `anio`,
`mes` (0 = all months), and an optional `cliente` filter, reading only from
`panacea_sales_v2`, and returning per-week, per-client sales quantity
(split into morning/afternoon) and subtotal figures, including `TOTAL` and
`SUBTOTAL` aggregate rows.

#### Scenario: Sales for a specific client and month
- **WHEN** a client calls
  `GET /get_ventas_por_cliente?anio=2026&mes=7&cliente=Panacea+Cordoba`
- **THEN** the response includes only rows for that named client (plus the
  `TOTAL` row), broken out by week-of-month, for July 2026

#### Scenario: All months when mes=0
- **WHEN** a client calls `GET /get_ventas_por_cliente?anio=2026&mes=0`
- **THEN** the response includes sales across all months of 2026
