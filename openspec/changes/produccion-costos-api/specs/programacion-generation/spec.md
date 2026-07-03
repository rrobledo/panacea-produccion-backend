## ADDED Requirements

### Requirement: Programacion pivot read
The system SHALL provide `GET /programacion` accepting `anio` (default
2025), `mes` (default 9), optional `responsable`, and optional `semana`
query parameters, and returning per-product rows with `{YYYYMMDD}-P`
(planned) and `{YYYYMMDD}-E`(executed/`prod`) fields for each matching day,
plus `producto_nombre`, `planeado` (the month's `corregido` planning
value), `responsable`, and `venta` (that month's sales count).

#### Scenario: Fetch a month's schedule
- **WHEN** a client calls `GET /programacion?anio=2026&mes=7`
- **THEN** the response includes one row per product scheduled in July
  2026, with day-keyed plan/executed fields for each business day

#### Scenario: Filter by responsable and week
- **WHEN** a client calls
  `GET /programacion?anio=2026&mes=7&responsable=Panaderia&semana=2`
- **THEN** only rows for products with `responsable = "Panaderia"` are
  returned, restricted to days in week 2 of that month

### Requirement: Programacion bulk cell edit
The system SHALL provide `POST /programacion` accepting a list of
per-product edits (each keyed by product `id`, optionally `responsable`,
and one or more `{YYYYMMDD}-P` / `{YYYYMMDD}-E` keys) and SHALL update the
product's `responsable` and the specified day rows' `plan`/`prod` fields,
returning 204 on success. A blank string value SHALL be treated as `null`.

#### Scenario: Edit a day's planned quantity
- **WHEN** a client calls `POST /programacion` with
  `[{"id": 42, "responsable": "Todos", "20260715-P": 80}]` and a valid
  `X-API-Key` header
- **THEN** the programacion row for `producto_id=42`, `fecha=2026-07-15`
  has `plan = 80`, and product 42's `responsable` is set to "Todos"

### Requirement: Programacion columns metadata
The system SHALL provide `GET /programacion_columnas` accepting `anio`,
`mes`, and optional `semana` query parameters and returning a week/day
column-group structure suitable for driving a pivoted grid UI, matching the
reference backend's structure (weeks computed relative to the 2nd of the
given month, matching the reference implementation's week-numbering
convention).

#### Scenario: Fetch column metadata for a month
- **WHEN** a client calls `GET /programacion_columnas?anio=2026&mes=7`
- **THEN** the response groups business days of July 2026 into weekly
  column groups

### Requirement: Monthly day-row generation
The system SHALL provide `POST /programacion/generate` accepting `year`,
`month` (both defaulting to the current year/month), `prev_year`,
`prev_month` (both defaulting to the previous calendar month, with year
rollover when `month = 1`), an optional `producto_id`, and a `dry_run` flag
defaulting to `true`. For every business day (Monday-Saturday) in `month`,
and for every eligible product (has at least one `costos_planificacion`
row, `habilitado = true`, `is_producto = true`; or, when `producto_id` is
given, exactly that product if it meets those three conditions), the system
SHALL insert a `costos_programacion` row (`responsable = "Todos"`,
`plan = null`, `prod = null`) for that day if one does not already exist
for that `(producto_id, fecha)` pair.

#### Scenario: Generate a month's day rows for all eligible products
- **WHEN** a client calls `POST /programacion/generate` with `year=2026`,
  `month=7`, `dry_run=false`
- **THEN** every business day in July 2026 gets a `costos_programacion` row
  for every enabled, `is_producto=true` product enrolled in planning, that
  doesn't already have one

#### Scenario: Reject an ineligible single-product scope
- **WHEN** a client calls `POST /programacion/generate` with
  `producto_id=42` for a product that has no `costos_planificacion` rows,
  is not `habilitado`, or is not `is_producto`
- **THEN** the system responds with 400 and does not silently generate zero
  rows

### Requirement: Month-over-month corregido correction
The system SHALL, as part of `POST /programacion/generate`, for every
product with at least one `costos_planificacion` row (or, when
`producto_id` is given, exactly that product), compute `prev_plan` and
`prev_corr` as the
`plan`/`corregido` values from that product's `prev_year`/`prev_month`
planning row, `prev_prod` as the sum of that product's `prev_year`/
`prev_month` programacion `prod` values, `prev_venta` as the sum of that
product's `prev_year`/`prev_month` `panacea_sales_v2` counts, and `plan` as
that product's `year`/`month` planning `plan` value. The system SHALL then
compute `corregido` as:
- `0`, if `prev_venta = 0`, or `prev_plan` is missing/`<= 0`, or
  `prev_corr` is missing/`<= 0`;
- otherwise, letting `scale = (plan, falling back to prev_venta if missing)
  / (prev_plan, falling back to prev_venta if missing)`:
  - if `prev_venta / prev_corr > 0.75` and `prev_venta >= prev_corr`:
    `corregido = int(scale × prev_venta)`
  - if `prev_venta / prev_corr > 0.75` and `prev_venta < prev_corr`:
    `corregido = int(scale × prev_corr)`
  - if `prev_venta / prev_corr <= 0.75`:
    `corregido = int(scale × prev_venta + (prev_corr - prev_venta) / 2)`

The system SHALL then update that product's `year`/`month`
`costos_planificacion` row's `corregido` **and** `sistema` fields to this
value, only if that row already exists (no-op otherwise).

#### Scenario: Zero guard on missing or non-positive prior data
- **WHEN** correcting a product whose `prev_corr` planning value is 0 or
  null
- **THEN** `corregido` is set to 0 for that product's current-month
  planning row

#### Scenario: High-performing correction branch
- **WHEN** a product's `prev_venta / prev_corr` ratio is above 0.75 and
  `prev_venta >= prev_corr`
- **THEN** `corregido = int(scale × prev_venta)` using the scale defined
  above

#### Scenario: Under-target correction branch
- **WHEN** a product's `prev_venta / prev_corr` ratio is 0.75 or below
- **THEN** `corregido = int(scale × prev_venta + (prev_corr - prev_venta) / 2)`

#### Scenario: Sistema is overwritten by correction
- **WHEN** `POST /programacion/generate` runs the correction step for a
  product/month that already had a `sistema` value from
  `planning/generate`
- **THEN** the `sistema` field is overwritten with the newly computed
  `corregido` value (this is intentional: `sistema` reflects the latest
  system-computed figure, correction included)

### Requirement: Scoped single-product generation for onboarding
`POST /programacion/generate` and `POST /planning/generate` SHALL, when
called with `producto_id` set, apply their respective generation logic to
only that product, producing the same rows that the bulk (all-products)
call would have produced for that product alone, so that onboarding a new
product is: create it, then call both endpoints scoped to its id.

#### Scenario: Onboard a new product
- **WHEN** a new product is created via `POST /productos`, then
  `POST /planning/generate?producto_id={id}` and
  `POST /programacion/generate?producto_id={id}` are both called with
  `dry_run=false`
- **THEN** the new product ends up with the same planning and programacion
  rows it would have if it had been included in a full bulk generation run

### Requirement: Copy week's plan values
The system SHALL provide `POST /programacion/copy-week` accepting required
`from_year`, `from_week`, `to_year`, `to_week` parameters (ISO week
numbers) and a `dry_run` flag defaulting to `true`. For every
`costos_programacion` row in the target week (`to_year`/`to_week`), the
system SHALL look up a source row in the source week
(`from_year`/`from_week`) with the same `producto_id` and the same
day-of-week. If a match is found, the target row's `plan` is set to the
source row's `plan`. If no match is found, the target row is left
unchanged (skipped) — it SHALL NOT be nulled out.

#### Scenario: Copy matched days
- **WHEN** a client calls `POST /programacion/copy-week` with
  `from_year=2026, from_week=26, to_year=2026, to_week=27, dry_run=false`
- **THEN** every target-week row whose product also has a same-weekday row
  in source week 26 has its `plan` overwritten with that source row's
  `plan`

#### Scenario: Unmatched target rows are left untouched
- **WHEN** a target-week row's product has no matching product+weekday row
  in the source week
- **THEN** that target row's `plan` value is unchanged after the copy
  operation completes

#### Scenario: Reject same source and target week
- **WHEN** `from_year/from_week` equals `to_year/to_week`
- **THEN** the system responds with 400 rather than performing a no-op copy

### Requirement: Automatic monthly cascade via scheduled trigger
The system SHALL run a daily scheduled job that, only when the current date
is the last day of the current month, calls the monthly day-row generation
and correction logic (equivalent to `POST /programacion/generate` with
`dry_run=false`) for the upcoming month, using the closing month as
`prev_year`/`prev_month`. The scheduled job SHALL authenticate using a
dedicated cron secret distinct from the general API key, and SHALL surface
(not swallow) any failure so platform-level cron failure alerting captures
it.

#### Scenario: Skip on non-last-day
- **WHEN** the daily scheduled job runs on a day that is not the last day
  of the month
- **THEN** it performs no generation and reports that it was skipped

#### Scenario: Run on last day of month
- **WHEN** the daily scheduled job runs on the last day of the month
- **THEN** it generates next month's day rows and correction using this
  month as the "previous" period, equivalent to an on-demand
  `POST /programacion/generate` call for next month

#### Scenario: Cron endpoint rejects non-cron callers
- **WHEN** a request to the scheduled-job endpoint does not include a valid
  cron secret
- **THEN** the system responds with 401/403 even if a valid general API key
  is presented instead

### Requirement: Dry-run default on mutating generation endpoints
The system SHALL default `dry_run` to `true` on `POST /planning/generate`,
`POST /programacion/generate`, and `POST /programacion/copy-week` when the
parameter is omitted, so that calling any of these endpoints without
explicitly passing `dry_run=false` never writes to the database.

#### Scenario: Omitted dry_run defaults to read-only preview
- **WHEN** a client calls any of the three generation endpoints without a
  `dry_run` parameter
- **THEN** the system treats the call as `dry_run=true` and does not
  mutate any data
