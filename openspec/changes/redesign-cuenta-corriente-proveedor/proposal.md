## Why

`CuentaCorrienteProveedor` today is a single table doing three jobs at once
(factura, pago, and the Debe/Haber ledger derived by mixing both), with
`iva`/`percepcion` as flat total amounts (no alícuota/tipo breakdown), no
comprobante type (Factura A/B/C/M, ND, NC), no split payment methods, no
Órdenes de Compra, and receipt photos stored as base64 in deferred text
columns (~1GB across ~900 production rows). This blocks the fiscal
reporting (Libro IVA Compras, percepciones discriminadas por tipo) the
business actually needs, and the payment model can't represent a single
payment split across multiple media (e.g. transferencia + cheque) or track
cheque `fecha_acreditacion`.

Now is the right time to fix this at the model level rather than patch it
further: the new frontend (`panacea-produccion`) that will consume this API
is young (~12 files touch this shape, no global/cached state), the current
production data volume is small (~900 rows), and no fiscal-detail UI has
been built yet anywhere to migrate away from — building it once against
the right contract is cheaper than building it against the flat shape and
reshaping later.

## What Changes

- **BREAKING**: Replace `CuentaCorrienteProveedor` /
  `CuentaCorrienteProveedorAfect` / `CuentaCorrienteProveedorDetalle` as the
  system of record with a normalized model: `Compra` (cabecera),
  `CompraDetalle` (renglones; each row is exactly one of `tipo=INSUMO`
  (references a catalog `Insumo` via `insumo_id`), `tipo=ITEM_GASTO`
  (references the new `ItemGasto` catalog via `item_gasto_id`), or
  `tipo=LIBRE` (free-text `descripcion` only, no catalog reference) — plus
  `alicuota_iva` and `centro_costo_id`/`cuenta_contable_id` as reserved
  nullable FKs, no logic yet), `CompraImpuesto` (generic `tipo`/
  `base_imponible`/`porcentaje`/`importe` — covers every IVA alícuota,
  percepción, and impuesto interno without schema changes when a new tax
  type appears), and `CompraAdjunto` (attachment metadata + URL, replacing
  the base64 columns).
- **New**: `ItemGasto`, a lightweight catalog of reusable expense concepts
  (e.g. "Flete", "Alquiler") — `codigo`, `nombre`, `activo`. Unlike
  `Insumo`, it carries no pricing/stock fields; it exists solely to be
  referenced from `CompraDetalle.item_gasto_id` so recurring non-insumo
  expenses don't have to be re-typed as free text every time.
- **BREAKING**: Replace the single-table pago rows with `Pago` (cabecera),
  `PagoMedio` (a payment split across multiple methods — transferencia,
  cheque, echeq, efectivo, tarjeta — each with its own `importe`, and for
  cheque/echeq a `banco`/`numero`/`fecha_acreditacion`), and
  `PagoAplicacion` (N:M pago↔compra, direct generalization of the existing
  `CuentaCorrienteProveedorAfect` linkage/trigger pattern).
- **New**: `MovimientoCC`, an append-only ledger (fecha, tipo, documento,
  debe, haber) fed by `Compra` and `Pago` — the Cuenta Corriente balance is
  always computed from this ledger, never stored.
- **New**: `LibroIvaCompra`, derived from `Compra`/`CompraImpuesto` per
  período (neto, iva21/105/27, exento, no gravado, percepciones); derived
  by default, materializable later if read performance requires it.
- **New**: `OrdenCompra` / `OrdenCompraDetalle` (cabecera + renglones with
  `cantidad_pedida`/`cantidad_recibida`). A `Compra` gets an optional
  `orden_compra_id`; creating it accumulates `cantidad_recibida` and
  advances `OrdenCompra.estado` (`PENDIENTE` → `PARCIAL` → `RECIBIDA`). No
  separate goods-receipt module in this change.
- **Modified**: `Proveedor` gains `codigo`, `nombre_fantasia`,
  `condicion_iva`, `condicion_pago` (default, overridable per `Compra`).
- **New dependency**: object storage (Vercel Blob) for `CompraAdjunto`;
  requires a new env var and a one-time migration of the ~900 existing
  base64 images out of the database.
- **Data migration**: one-time, big-bang script moves the ~900 existing
  `costos_cuentacorrienteproveedor` rows into the new tables (`FACTURA` →
  `Compra`, `PAGO` + its `Afect` rows → `Pago`/`PagoAplicacion`). Historical
  `iva`/`percepcion` totals become a single `CompraImpuesto` row tagged
  `tipo=HISTORICO_SIN_DESGLOSE` per compra — the original alícuota/tipo
  breakdown was never captured and cannot be reconstructed. Old tables are
  kept, read-only, as historical archive (not dropped) — `panacea-backend`
  (Django, `managed=True` models on these tables) keeps running unmodified
  reads; only this service stops writing to them.
- **Explicitly out of scope**: accounting integration (asiento generation,
  `CUENTA_CONTABLE`/`CENTRO_COSTO` stay as reserved nullable FKs with no
  behavior), multi-currency (no `moneda`/`cotizacion` fields), goods-receipt
  module beyond `OrdenCompra`'s own `cantidad_recibida` counter.

## Capabilities

### New Capabilities
- `compras`: comprobante registration (Factura A/B/C/M, ND, NC, tickets,
  gastos) with automatic neto/IVA/percepciones/total calculation via
  `CompraImpuesto`, detalle lines that reference an `Insumo`, an
  `ItemGasto`, or free text (`CompraDetalle.tipo`), a CRUD catalog for
  `ItemGasto` (`/costos/items-gasto`), and attachment upload to object
  storage.
- `tesoreria-pagos`: payment registration with multiple payment media per
  payment and application (full/partial, single or multiple facturas) via
  `PagoAplicacion`.
- `ordenes-compra`: purchase order CRUD and reception tracking against
  incoming `Compra` records.
- `libro-iva-compras`: derived VAT purchase ledger report by período.

### Modified Capabilities
- `proveedores-cuenta-corriente`: `Proveedor` gains fiscal/commercial
  fields (`codigo`, `nombre_fantasia`, `condicion_iva`, `condicion_pago`);
  the Cuenta Corriente ledger changes from a single mixed-role table to a
  derived read from `MovimientoCC`, fed by the new `Compra`/`Pago` models
  instead of `CuentaCorrienteProveedor`/`Afect`. All existing
  `/costos/ctacteprov*` request/response contracts are replaced (breaking).

## Impact

- **Backend code**: new `app/models`, `app/schemas`, `app/services`,
  `app/routers` for `Compra`, `Pago`, `OrdenCompra`, `MovimientoCC`,
  `LibroIvaCompra`; removal of `app/{models,schemas,services,routers}/
  cuenta_corriente.py` from the write path (kept only for reading the
  archived legacy tables if needed); `app/routers/proveedores.py` and its
  schema extended.
- **Database**: new migration (`migrations/000N_*.sql`, mirrored into
  `docker/init-db/`) creating the new tables; a one-time data-migration
  script for the ~900-row backfill; no `DROP TABLE` on the legacy schema.
- **`panacea-backend` (Django)**: no code change required — it keeps its
  `managed=True` models over the now-frozen legacy tables; someone should
  still be told writes will stop landing there going forward.
- **`panacea-produccion` (frontend)**: breaking — the ~12 files under
  `src/pages/facturas/**`, `src/pages/proveedores/**`, and
  `DashboardPage.jsx` need to be rewritten against the new endpoints/shape;
  new screens needed for `OrdenCompra`, Libro IVA report, the
  multi-método payment form, and an `ItemGasto` catalog admin screen (CRUD
  at `/costos/items-gasto`, same shape as the existing `Insumo` catalog
  screen). The compra detalle line editor needs a per-row selector between
  Insumo (autocomplete against `/costos/insumos`), Item de Gasto
  (autocomplete against `/costos/items-gasto`), and texto libre — see
  `specs/compras/spec.md`'s "Compra detalle" requirement for the exact
  field/validation contract.
- **New external dependency**: Vercel Blob (or equivalent) for
  `CompraAdjunto`; new required env var.
- **Tests**: existing `tests/unit/test_cuenta_corriente_service.py`,
  `test_ctacteprov_api.py`, `test_ctacteprov_detalle_insumos.py` retired in
  favor of new suites per capability; the trigger-based integration test
  pattern (real DB, not mocked) carries over to `PagoAplicacion`.
