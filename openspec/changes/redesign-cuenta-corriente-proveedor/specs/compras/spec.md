## ADDED Requirements

### Requirement: Compra CRUD
The system SHALL provide `GET/POST /costos/compras` and
`GET/PUT/PATCH/DELETE /costos/compras/{id}` for the `Compra` resource:
`proveedor_id`, `tipo_comprobante` in `{FACTURA_A, FACTURA_B, FACTURA_C,
FACTURA_M, NOTA_CREDITO, NOTA_DEBITO, TICKET, GASTO}`, `punto_venta`,
`numero`, `fecha`, `fecha_vencimiento`, `condicion_pago` (defaults from
the proveedor's `condicion_pago` if not provided), `observaciones`, and
the computed totals `subtotal`, `iva`, `percepciones`, `impuestos`,
`total` (derived from `CompraDetalle` and `CompraImpuesto` rows, see
below). `orden_compra_id` is optional; when set, see the `ordenes-compra`
spec for reception behavior. `estado` and `saldo_pendiente` are
system-managed (see "Compra saldo pendiente" below), not client-writable.

#### Scenario: Create a compra with detalle and impuestos
- **WHEN** a client calls `POST /costos/compras` with a `proveedor_id`,
  `tipo_comprobante=FACTURA_A`, one or more `detalle` rows, and one or
  more `impuestos` rows
- **THEN** the system creates the `Compra` and its `CompraDetalle`/
  `CompraImpuesto` rows in the same request, and computes `subtotal`,
  `iva`, `percepciones`, `impuestos`, and `total` from them

#### Scenario: Contado compra is immediately settled
- **WHEN** a client calls `POST /costos/compras` with
  `condicion_pago=CONTADO`
- **THEN** the system sets `saldo_pendiente=0` and `estado=PAGADO` on
  creation, without requiring a separate `Pago`

#### Scenario: Cuenta corriente compra starts pending
- **WHEN** a client calls `POST /costos/compras` with
  `condicion_pago=CUENTA_CORRIENTE`
- **THEN** the system sets `saldo_pendiente=total` and `estado=PENDIENTE`

### Requirement: Compra detalle
`CompraDetalle` rows SHALL belong to exactly one `Compra` and SHALL
capture `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `descuento`,
`alicuota_iva`, `importe_neto`, `importe_iva`, `importe_total`, and
optional, currently-unused `centro_costo_id`/`cuenta_contable_id`
references reserved for a future accounting capability. `tipo` SHALL be
one of `INSUMO` (references a `costos_insumos` row via `insumo_id`),
`ITEM_GASTO` (references a `compras_item_gasto` row via `item_gasto_id`),
or `LIBRE` (free-text `descripcion` only, no catalog reference). Exactly
one of the catalog references SHALL be set, matching `tipo`; `descripcion`
SHALL be required when `tipo=LIBRE` and, when `tipo` is `INSUMO` or
`ITEM_GASTO`, defaults to the referenced catalog row's `nombre` if not
provided by the client (a snapshot taken at creation time, so later
renames of the catalog entry don't retroactively change historical
compras).

#### Scenario: Add a detalle row to a compra
- **WHEN** a client calls `POST /costos/compras/{id}/detalle` with
  `descripcion`, `cantidad`, `precio_unitario`, and `alicuota_iva`
- **THEN** the system creates the row and recomputes the parent
  `Compra`'s `subtotal`/`iva`/`total`

#### Scenario: Reference a catalog insumo without overriding descripcion
- **WHEN** a client calls `POST /costos/compras/{id}/detalle` with
  `tipo=INSUMO` and `insumo_id` set, and no `descripcion`
- **THEN** the system snapshots the referenced `Insumo`'s `nombre` as the
  row's `descripcion`

#### Scenario: Reference a catalog item de gasto
- **WHEN** a client calls `POST /costos/compras/{id}/detalle` with
  `tipo=ITEM_GASTO` and `item_gasto_id` set
- **THEN** the system creates the row referencing that `ItemGasto`, using
  its `nombre` as `descripcion` unless the client provided one

#### Scenario: Reject a detalle row with an unknown insumo_id
- **WHEN** a client calls `POST /costos/compras/{id}/detalle` with
  `tipo=INSUMO` and an `insumo_id` that doesn't exist
- **THEN** the system responds with 404 and does not create the row

#### Scenario: Reject a LIBRE detalle row without descripcion
- **WHEN** a client calls `POST /costos/compras/{id}/detalle` with
  `tipo=LIBRE` (or omitted) and no `descripcion`
- **THEN** the system responds with 400 and does not create the row

### Requirement: Item de gasto catalog
The system SHALL provide `GET/POST /costos/items-gasto` and
`GET/PUT/DELETE /costos/items-gasto/{id}` for the `ItemGasto` resource:
`codigo` (optional), `nombre`, `activo`. `GET /costos/items-gasto` SHALL
support filtering by `nombre` (case-insensitive substring match). This
catalog exists solely to be referenced from `CompraDetalle.item_gasto_id`
— it has no pricing or stock fields, unlike `Insumo`.

#### Scenario: Create and list items de gasto
- **WHEN** a client calls `POST /costos/items-gasto` with `nombre=Flete`
- **THEN** the system creates the `ItemGasto` row, and it subsequently
  appears in `GET /costos/items-gasto`

### Requirement: Compra impuestos
`CompraImpuesto` rows SHALL belong to exactly one `Compra` and SHALL
capture `tipo`, `base_imponible`, `porcentaje`, `importe`. `tipo` SHALL
be validated against a fixed vocabulary (`IVA_21`, `IVA_10_5`, `IVA_27`,
`PERCEPCION_IVA`, `PERCEPCION_IIBB`, `PERCEPCION_MUNICIPAL`,
`RETENCION_IVA`, `RETENCION_GANANCIAS`, `RETENCION_SUSS`,
`IMPUESTOS_INTERNOS`, `HISTORICO_SIN_DESGLOSE`) — introducing a new tax
type SHALL NOT require a schema change, only adding it to this
vocabulary.

#### Scenario: Reject an unknown impuesto tipo
- **WHEN** a client calls `POST /costos/compras/{id}/impuestos` with a
  `tipo` not in the fixed vocabulary
- **THEN** the system responds with 400 and does not create the row

#### Scenario: Historical migration marks amounts as undiscriminated
- **WHEN** the data-migration script backfills a legacy
  `costos_cuentacorrienteproveedor` row's flat `iva`/`percepcion` totals
- **THEN** it creates a single `CompraImpuesto` row with
  `tipo=HISTORICO_SIN_DESGLOSE` for that amount, not a fabricated
  per-alícuota split

### Requirement: Compra adjuntos
The system SHALL provide `POST /costos/compras/{id}/adjuntos` accepting
a file upload, storing it in object storage, and creating a
`CompraAdjunto` row (`nombre`, `url`, `tipo`, `fecha`) referencing the
stored file's URL. `GET /costos/compras/{id}` SHALL include the compra's
`adjuntos` list. A failed upload SHALL NOT roll back or block the parent
`Compra`.

#### Scenario: Upload a receipt photo
- **WHEN** a client calls `POST /costos/compras/42/adjuntos` with an
  image file
- **THEN** the system uploads it to object storage and creates a
  `CompraAdjunto` row with the resulting `url`, without storing the file
  content in the database

### Requirement: Compra saldo pendiente
`Compra.saldo_pendiente` SHALL be maintained by a database trigger on
`PagoAplicacion` insert/delete/update — application code SHALL NOT
recompute or duplicate this arithmetic. `Compra.estado` SHALL be
`PAGADO` when `saldo_pendiente <= 0`, else `PENDIENTE` (or `PARCIAL` if
`0 < saldo_pendiente < total`).

#### Scenario: Applying a pago decrements saldo_pendiente
- **WHEN** a `PagoAplicacion` row is inserted linking a `Pago` of amount
  `X` to a `Compra`
- **THEN** the trigger decrements that `Compra`'s `saldo_pendiente` by
  `X` and updates `estado` accordingly, without any application code
  performing the same decrement

#### Scenario: Deleting a pago aplicacion restores saldo_pendiente
- **WHEN** a `PagoAplicacion` row is deleted
- **THEN** the trigger restores the linked `Compra`'s `saldo_pendiente`
  by the deleted row's `importe` and recomputes `estado`
