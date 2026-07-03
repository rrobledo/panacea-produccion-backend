## ADDED Requirements

### Requirement: Proveedores CRUD
The system SHALL provide `GET/POST /proveedores` and
`GET/PUT/PATCH/DELETE /proveedores/{id}` for the `Proveedor` resource
(`nombre`, `cuit` unique, `direccion`, `telefono`, `email`, `fecha_alta`
auto-set on creation, `estado` in `{activo, inactivo}`, default `activo`).
`GET /proveedores` SHALL support `nombre` (substring) and `estado` filters
(`estado=ALL` returns all), ordered by `nombre` by default.

#### Scenario: Create a proveedor
- **WHEN** a client calls `POST /proveedores` with a unique `cuit`
- **THEN** the system creates the row with `estado=activo` by default and
  `fecha_alta` set to the creation date

#### Scenario: Reject duplicate cuit
- **WHEN** a client calls `POST /proveedores` with a `cuit` that already
  exists
- **THEN** the system responds with 400/409 and does not create a
  duplicate row

### Requirement: Cuenta corriente proveedor CRUD
The system SHALL provide `GET/POST /ctacteprov` and
`GET/PUT/PATCH/DELETE /ctacteprov/{id}` for `CuentaCorrienteProveedor`
entries (`tipo_movimiento` in `{FACTURA, PAGO}`, `numero`, `fecha_emision`,
`fecha_vencimiento`, `importe_total`, `importe_pendiente`, `categoria`,
`tipo_pago`, `caja`, `estado`, optional receipt images). `GET /ctacteprov`
SHALL support `fecha_desde`, `fecha_hasta` (inclusive range on
`fecha_emision`), and `estado` (`TODOS` = all) filters, ordered by
`fecha_emision`.

#### Scenario: Create a factura on cuenta corriente
- **WHEN** a client calls `POST /ctacteprov` with
  `tipo_movimiento=FACTURA, tipo_pago=CUENTA_CORRIENTE, importe_total=1000`
- **THEN** the system sets `importe_pendiente=1000` and leaves `estado` at
  its default (pending)

#### Scenario: Immediate-payment factura is marked paid
- **WHEN** a client calls `POST /ctacteprov` with
  `tipo_movimiento=FACTURA, tipo_pago=EFECTIVO` (or `TRANSFERENCIA`)
- **THEN** the system sets `estado=PAGADO` and `importe_pendiente=0`

#### Scenario: Register a payment against a factura
- **WHEN** a client calls `POST /ctacteprov` with `tipo_movimiento=PAGO`
  and a `factura_id` referencing an existing factura
- **THEN** the system creates the payment entry with
  `importe_pendiente = importe_total`, and records a linkage between the
  payment and that factura for the amount paid

### Requirement: Payments nested under a factura
The system SHALL provide `GET /ctacteprov/{factura_id}/pagos` returning
only `CuentaCorrienteProveedor` entries with `tipo_movimiento=PAGO` linked
to that factura via the payment linkage recorded at payment creation time.

#### Scenario: List payments for a factura
- **WHEN** a client calls `GET /ctacteprov/10/pagos`
- **THEN** the response includes only payment entries linked to factura 10

### Requirement: Cuenta corriente summary
The system SHALL provide `GET /ctacteprovresumen` accepting `fecha_desde`
and `fecha_hasta` query parameters and returning
`total_facturas_pendientes` (sum of `importe_pendiente` across all
`FACTURA`/`CUENTA_CORRIENTE` entries, independent of the date range) and
`total_gastos` (sum of `importe_total` across entries within the date range
that are either non-cuenta-corriente facturas or any payment).

#### Scenario: Fetch summary for a date range
- **WHEN** a client calls
  `GET /ctacteprovresumen?fecha_desde=2026-01-01&fecha_hasta=2026-01-31`
- **THEN** the response includes `total_facturas_pendientes` and
  `total_gastos` computed as defined above
