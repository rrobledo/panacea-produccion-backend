## ADDED Requirements

### Requirement: Pago CRUD
The system SHALL provide `GET/POST /costos/pagos` and
`GET/PUT/PATCH/DELETE /costos/pagos/{id}` for the `Pago` resource:
`proveedor_id`, `fecha`, `importe` (SHALL equal the sum of its
`PagoMedio` rows' `importe`), `estado`, `observaciones`.

#### Scenario: Create a pago with a single medio
- **WHEN** a client calls `POST /costos/pagos` with `proveedor_id`,
  `fecha`, and one `medios` entry of `tipo=EFECTIVO`
- **THEN** the system creates the `Pago` and its `PagoMedio` row, with
  `Pago.importe` equal to that medio's `importe`

#### Scenario: Reject mismatched medios total
- **WHEN** a client calls `POST /costos/pagos` with an `importe` that
  does not equal the sum of the provided `medios`' `importe`
- **THEN** the system responds with 400 and does not create the `Pago`

### Requirement: Pago medio
`PagoMedio` rows SHALL belong to exactly one `Pago` and SHALL capture
`tipo` in `{TRANSFERENCIA, CHEQUE, ECHEQ, EFECTIVO, TARJETA}` and
`importe`. When `tipo` is `CHEQUE` or `ECHEQ`, `banco`, `numero`, and
`fecha_acreditacion` SHALL be required; for other tipos these fields
SHALL be omitted or null.

#### Scenario: Split a pago across two medios
- **WHEN** a client calls `POST /costos/pagos` with
  `medios=[{tipo: TRANSFERENCIA, importe: 500}, {tipo: CHEQUE, importe:
  500, banco: "Galicia", numero: "123", fecha_acreditacion:
  "2026-08-01"}]`
- **THEN** the system creates both `PagoMedio` rows under the same
  `Pago`

#### Scenario: Reject a cheque medio without banking fields
- **WHEN** a client calls `POST /costos/pagos` with a `medios` entry of
  `tipo=CHEQUE` missing `banco`, `numero`, or `fecha_acreditacion`
- **THEN** the system responds with 400 and does not create the `Pago`

### Requirement: Payments applied to a compra
The system SHALL provide `POST /costos/pagos/{id}/aplicaciones` to link
a `Pago` to one or more `Compra` rows via `PagoAplicacion`
(`pago_id`, `compra_id`, `importe`), and
`GET /costos/compras/{id}/pagos` returning every `Pago` with at least
one `PagoAplicacion` against that compra.

#### Scenario: Apply one pago to multiple facturas
- **WHEN** a client calls `POST /costos/pagos/7/aplicaciones` with
  `[{compra_id: 1, importe: 200}, {compra_id: 2, importe: 100}]`
- **THEN** the system creates two `PagoAplicacion` rows, and the trigger
  decrements `saldo_pendiente` on both compras (see the `compras` spec's
  "Compra saldo pendiente" requirement)

#### Scenario: List payments for a compra
- **WHEN** a client calls `GET /costos/compras/1/pagos`
- **THEN** the response includes only `Pago` entries with a
  `PagoAplicacion` linking them to compra 1
