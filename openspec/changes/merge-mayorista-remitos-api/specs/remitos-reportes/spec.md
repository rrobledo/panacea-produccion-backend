## ADDED Requirements

### Requirement: List all remitos ordered by delivery date
The system SHALL provide `GET /costos/remitos-reportes/pendientes-entrega`
returning every remito regardless of estado, ordered by `fecha_entrega`
ascending. No filter is applied on `fecha_recibido`/`fecha_facturacion` —
this matches mayorista's current actual behavior (both filters were
deliberately removed there in commits `13b8d18` and `74ed0c0`); the
"pendientes" name is kept for continuity but no longer implies filtering.
The endpoint SHALL NOT require authentication (read-only, consistent with
other read endpoints under `/costos`).

#### Scenario: All remitos are returned regardless of estado
- **WHEN** a caller requests `GET /costos/remitos-reportes/pendientes-entrega`
  and the database has remitos in every estado (`PENDIENTE` through
  `ENTREGADO`)
- **THEN** the response includes every remito, ordered by `fecha_entrega`
  ascending

#### Scenario: No remitos
- **WHEN** the database has no remitos
- **THEN** the response is an empty list with status 200

### Requirement: Group all remitos by delivery day
The system SHALL provide `GET /costos/remitos-reportes/pendientes-por-dia`,
returning the same unfiltered set as pendientes-entrega, grouped by the date
portion of `fecha_entrega`, each group carrying per-estado counts (pendiente,
en preparación, listo para entrega, en camino, entregado) and the list of
remitos in that group. The endpoint SHALL accept optional `fecha_desde` and
`fecha_hasta` query parameters filtering on `fecha_entrega`, and SHALL NOT
require authentication.

#### Scenario: Grouping and counts across all estados
- **WHEN** there are remitos scheduled for delivery on two different days,
  in different estados including `ENTREGADO`
- **THEN** the response contains one group per distinct delivery day, sorted
  by date ascending, each with `total_remitos` equal to the group's remito
  count and per-estado counts (including entregados) summing to
  `total_remitos`

#### Scenario: Filtering by date range
- **WHEN** a caller passes `fecha_desde` and/or `fecha_hasta`
- **THEN** only remitos with `fecha_entrega` within `[fecha_desde,
  fecha_hasta]` (inclusive, either bound optional) are included in the
  grouped result

### Requirement: Group pending product quantities by delivery day and responsable
The system SHALL provide
`GET /costos/remitos-reportes/productos-pendientes-por-dia`, returning
pending product quantities (`cantidad - entregado`, treating a null
`entregado` as 0) for remitos not yet invoiced (`fecha_facturacion` is null),
grouped first by the date portion of `fecha_entrega`, then by
`Productos.responsable`, listing each pending producto's name and pending
quantity. The endpoint SHALL accept optional `fecha_desde`/`fecha_hasta`
filters on `fecha_entrega`, and SHALL NOT require authentication.

#### Scenario: Grouping by day then responsable
- **WHEN** there are pending remito-detalle rows for productos with
  different `responsable` values, scheduled across multiple delivery days
- **THEN** the response has one entry per distinct delivery day (sorted
  ascending), each containing one entry per distinct `responsable` (sorted
  alphabetically), each listing that responsable's pending productos with
  their pending quantity summed across remitos

#### Scenario: Entregado partially fulfills a detalle line
- **WHEN** a remito-detalle line has `cantidad=10` and `entregado=4`
- **THEN** the pending quantity contributed by that line is 6

#### Scenario: Filtering by date range
- **WHEN** a caller passes `fecha_desde` and/or `fecha_hasta`
- **THEN** only remito-detalle rows whose remito's `fecha_entrega` falls
  within `[fecha_desde, fecha_hasta]` (inclusive, either bound optional) are
  included
