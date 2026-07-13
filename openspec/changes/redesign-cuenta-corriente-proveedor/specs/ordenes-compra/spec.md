## ADDED Requirements

### Requirement: Orden de compra CRUD
The system SHALL provide `GET/POST /costos/ordenes-compra` and
`GET/PUT/PATCH/DELETE /costos/ordenes-compra/{id}` for the
`OrdenCompra` resource: `proveedor_id`, `fecha`,
`fecha_entrega_estimada`, `observaciones`, `estado` in `{PENDIENTE,
PARCIAL, RECIBIDA, CERRADA, CANCELADA}` (system-managed after creation —
see "Recepción contra compra" below), and nested `detalle` rows
(`descripcion`/`insumo_id`, `cantidad_pedida`, `precio_unitario_estimado`,
and a system-managed `cantidad_recibida` starting at `0`).

#### Scenario: Create an orden de compra
- **WHEN** a client calls `POST /costos/ordenes-compra` with a
  `proveedor_id` and one or more `detalle` rows
- **THEN** the system creates the `OrdenCompra` with `estado=PENDIENTE`
  and each `OrdenCompraDetalle.cantidad_recibida` set to `0`

### Requirement: Recepción contra compra
Creating a `Compra` with `orden_compra_id` set SHALL increment the
matching `OrdenCompraDetalle.cantidad_recibida` rows and SHALL advance
the parent `OrdenCompra.estado` to `PARCIAL` (some but not all detalle
rows fully received) or `RECIBIDA` (all detalle rows' `cantidad_recibida
>= cantidad_pedida`).

#### Scenario: Partial reception
- **WHEN** a client calls `POST /costos/compras` with `orden_compra_id`
  referencing an `OrdenCompra` whose detalle rows are only partially
  covered by this compra's detalle
- **THEN** the system increments the matched `OrdenCompraDetalle`
  `cantidad_recibida` values and sets `OrdenCompra.estado=PARCIAL`

#### Scenario: Full reception
- **WHEN** the last outstanding `OrdenCompraDetalle` row for an
  `OrdenCompra` has its `cantidad_recibida` reach `cantidad_pedida` via
  a `Compra` creation
- **THEN** the system sets `OrdenCompra.estado=RECIBIDA`
