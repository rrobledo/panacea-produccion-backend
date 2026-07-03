## MODIFIED Requirements

### Requirement: Cuenta corriente proveedor CRUD
The system SHALL provide `GET/POST /ctacteprov` and
`GET/PUT/PATCH/DELETE /ctacteprov/{id}` for `CuentaCorrienteProveedor`
entries (`tipo_movimiento` in `{FACTURA, PAGO}`, `numero`, `fecha_emision`,
`fecha_vencimiento`, `importe_total`, `importe_pendiente`, `iva`,
`percepcion`, `categoria`, `tipo_pago`, `caja`, `estado`, optional receipt
images). `iva` and `percepcion` are optional on write and default to `0`.
`GET /ctacteprov` SHALL support `fecha_desde`, `fecha_hasta` (inclusive range
on `fecha_emision`), and `estado` (`TODOS` = all) filters, ordered by
`fecha_emision`. `POST /ctacteprov` SHALL accept an optional nested `insumos`
array (`{insumo, cantidad, subtotal}`); when present, each entry is created
as a `costos_cuentacorrienteproveedordetalle` row linked to the new entry in
the same request. `GET /ctacteprov/{id}` SHALL include the entry's `insumos`
detail rows in the response.

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

#### Scenario: Create a factura with iva and percepcion
- **WHEN** a client calls `POST /ctacteprov` with
  `tipo_movimiento=FACTURA, importe_total=1210, iva=210, percepcion=30`
- **THEN** the system stores `iva=210` and `percepcion=30` on the created
  entry alongside `importe_total`

#### Scenario: Create a factura without iva or percepcion
- **WHEN** a client calls `POST /ctacteprov` without `iva` or `percepcion` in
  the payload
- **THEN** the system defaults both `iva` and `percepcion` to `0`

#### Scenario: Create a factura with nested insumo detail
- **WHEN** a client calls `POST /ctacteprov` with
  `insumos=[{insumo: 5, cantidad: 10, subtotal: 500}]`
- **THEN** the system creates the `CuentaCorrienteProveedor` entry and one
  `costos_cuentacorrienteproveedordetalle` row linked to it with
  `insumo=5, cantidad=10, subtotal=500`

#### Scenario: Fetch a factura with its insumo detail
- **WHEN** a client calls `GET /ctacteprov/{id}` for an entry that has
  detail rows
- **THEN** the response includes an `insumos` array with each detail row's
  `insumo`, `cantidad`, and `subtotal`

### Requirement: Payments nested under a factura
The system SHALL provide `GET /ctacteprov/{factura_id}/pagos` returning
only `CuentaCorrienteProveedor` entries with `tipo_movimiento=PAGO` linked
to that factura via the payment linkage recorded at payment creation time.

#### Scenario: List payments for a factura
- **WHEN** a client calls `GET /ctacteprov/10/pagos`
- **THEN** the response includes only payment entries linked to factura 10
