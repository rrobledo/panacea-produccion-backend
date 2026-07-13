## MODIFIED Requirements

### Requirement: Proveedores CRUD
The system SHALL provide `GET/POST /proveedores` and
`GET/PUT/PATCH/DELETE /proveedores/{id}` for the `Proveedor` resource
(`codigo`, `nombre`, `nombre_fantasia`, `cuit` unique, `condicion_iva` in
`{RESPONSABLE_INSCRIPTO, MONOTRIBUTO, EXENTO, CONSUMIDOR_FINAL}`,
`condicion_pago` in `{CONTADO, CUENTA_CORRIENTE}` (default
`CUENTA_CORRIENTE`, used as the default `Compra.condicion_pago` when a
comprobante doesn't override it), `direccion`, `telefono`, `email`,
`fecha_alta` auto-set on creation, `estado` in `{activo, inactivo}`,
default `activo`). `GET /proveedores` SHALL support `nombre` (substring)
and `estado` filters (`estado=ALL` returns all), ordered by `nombre` by
default.

#### Scenario: Create a proveedor
- **WHEN** a client calls `POST /proveedores` with a unique `cuit` and a
  `condicion_iva`
- **THEN** the system creates the row with `estado=activo` by default,
  `fecha_alta` set to the creation date, and `condicion_pago` defaulted
  to `CUENTA_CORRIENTE` if not provided

#### Scenario: Reject duplicate cuit
- **WHEN** a client calls `POST /proveedores` with a `cuit` that already
  exists
- **THEN** the system responds with 400/409 and does not create a
  duplicate row

#### Scenario: Reject unknown condicion_iva
- **WHEN** a client calls `POST /proveedores` with a `condicion_iva`
  value outside `{RESPONSABLE_INSCRIPTO, MONOTRIBUTO, EXENTO,
  CONSUMIDOR_FINAL}`
- **THEN** the system responds with 400 and does not create the row

## REMOVED Requirements

### Requirement: Cuenta corriente proveedor CRUD
**Reason**: The single-table model mixing facturas and pagos in one
`CuentaCorrienteProveedor` row is replaced by the normalized `compras`
and `tesoreria-pagos` capabilities.
**Migration**: Use `POST/GET /costos/compras` and
`GET/PUT/PATCH/DELETE /costos/compras/{id}` to create/read/update/delete
comprobantes, and `POST/GET /costos/pagos` for payments — see the
`compras` and `tesoreria-pagos` specs.

### Requirement: Payments nested under a factura
**Reason**: `CuentaCorrienteProveedorAfect` is replaced by
`PagoAplicacion`, owned by the `tesoreria-pagos` capability.
**Migration**: Use `GET /costos/compras/{id}/pagos` (see the
`tesoreria-pagos` spec's "Payments applied to a compra" requirement)
instead of `GET /ctacteprov/{factura_id}/pagos`.

### Requirement: Cuenta corriente summary
**Reason**: Replaced by the derived ledger and resumen requirements added
to this same capability below, backed by `MovimientoCC` and
`Compra.saldo_pendiente` instead of `CuentaCorrienteProveedor`.
**Migration**: Use `GET /costos/proveedores/{id}/cuenta-corriente` for
the per-proveedor ledger, and `GET /costos/cuenta-corriente/resumen` for
the dashboard summary.

## ADDED Requirements

### Requirement: Cuenta corriente ledger
The system SHALL provide `GET /costos/proveedores/{id}/cuenta-corriente`
returning the Debe/Haber ledger for that proveedor: one row per
`MovimientoCC` entry (`fecha`, `tipo`, `documento`, `debe`, `haber`),
plus a running `saldo` computed as a cumulative sum ordered by
`fecha, id`. `saldo` SHALL NOT be a stored column; it SHALL be computed
at query time from `MovimientoCC` rows for that proveedor. The endpoint
SHALL support `fecha_desde`/`fecha_hasta` filters (inclusive range on
`fecha`).

#### Scenario: Fetch a proveedor's ledger
- **WHEN** a client calls `GET /costos/proveedores/10/cuenta-corriente`
- **THEN** the response includes every `MovimientoCC` row for proveedor
  10 ordered by `fecha, id`, each with a cumulative `saldo` computed from
  prior rows, and no separately stored balance is read

#### Scenario: Ledger reflects a payment application
- **WHEN** a `PagoAplicacion` is created linking a `Pago` to a `Compra`
  for proveedor 10
- **THEN** the next call to `GET /costos/proveedores/10/cuenta-corriente`
  includes the corresponding `haber` movement and the running `saldo`
  decreases by that amount from that point forward

### Requirement: Cuenta corriente resumen
The system SHALL provide `GET /costos/cuenta-corriente/resumen` accepting
`fecha_desde` and `fecha_hasta` query parameters and returning
`total_facturas_pendientes` (sum of `Compra.saldo_pendiente` across all
`Compra` rows with `condicion_pago=CUENTA_CORRIENTE`, independent of the
date range) and `total_gastos` (sum of `Compra.total` for compras within
the date range that are either `condicion_pago=CONTADO` or have at least
one applied `Pago`).

#### Scenario: Fetch summary for a date range
- **WHEN** a client calls
  `GET /costos/cuenta-corriente/resumen?fecha_desde=2026-01-01&fecha_hasta=2026-01-31`
- **THEN** the response includes `total_facturas_pendientes` and
  `total_gastos` computed as defined above
