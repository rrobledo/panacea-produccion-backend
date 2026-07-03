## Why

`costos_cuentacorrienteproveedor` (a supplier invoice/payment ledger row) currently
records only a single `importe_total` per row, with no breakdown of which
`insumos` (supplies) the invoice covers, at what quantity, or subtotal, and no
tax breakdown (`iva`, `percepcion`) separate from the total. Purchasing/costing
needs that detail to reconcile invoices against received supplies and to report
tax amounts separately from the goods subtotal — today that data isn't
captured anywhere and can't be added retroactively without a schema change.

## What Changes

- Add two columns to `costos_cuentacorrienteproveedor`: `iva` (float, tax
  amount) and `percepcion` (float, withholding/perception tax amount), both
  defaulting to `0` so existing rows remain valid.
- Add a new table, `costos_cuentacorrienteproveedordetalle`, holding the
  insumo-level breakdown of a `costos_cuentacorrienteproveedor` entry: a
  foreign key back to the parent row, a foreign key to `costos_insumos`, a
  `cantidad` (count), and a `subtotal`. Relationship is 1 (cuenta corriente
  entry) to many (detalle rows), on delete of the parent the detail rows are
  removed (`CASCADE`), mirroring how `RemitoDetalles` relates to `Remitos` in
  the reference schema.
- **Schema ownership**: per explicit decision (this service's DB access is
  otherwise read/write-only against the Django-owned schema), this specific
  DDL — the two new columns and the new table — is authored and applied as a
  SQL migration owned by this service (`panacea-produccion-backend`), not as a
  Django migration in `panacea-backend`. This is a deliberate, scoped
  exception; no other schema changes are implied.
- New API surface to populate and read the detail rows:
  - `POST /ctacteprov` accepts an optional nested `insumos` array
    (`{insumo, cantidad, subtotal}`) to create detail rows together with the
    parent entry in one call, and accepts `iva`/`percepcion` on the payload.
  - `GET /ctacteprov/{id}` response includes the nested `insumos` array.
  - `GET /ctacteprov/{id}/insumos` lists the detail rows for one entry.
  - `POST /ctacteprov/{id}/insumos` appends one or more detail rows to an
    existing entry (populate after the fact, not only at creation time).
  - `DELETE /ctacteprov/{id}/insumos/{detalle_id}` removes a single detail row
    (needed for correcting a mis-entered line without deleting the whole
    invoice).

## Capabilities

### New Capabilities
- `ctacteprov-insumos-detalle`: the `costos_cuentacorrienteproveedordetalle`
  table and its nested CRUD surface under `/ctacteprov/{id}/insumos`.

### Modified Capabilities
- `proveedores-cuenta-corriente` (defined, not yet implemented, in the
  in-flight `produccion-costos-api` change): the `CuentaCorrienteProveedor`
  resource gains `iva` and `percepcion` fields, and `POST /ctacteprov` /
  `GET /ctacteprov/{id}` payloads gain the nested `insumos` array described
  above.

## Impact

- **Database**: new columns on `costos_cuentacorrienteproveedor`
  (`iva`, `percepcion`, both `DOUBLE PRECISION DEFAULT 0`); new table
  `costos_cuentacorrienteproveedordetalle` (FKs to
  `costos_cuentacorrienteproveedor` and `costos_insumos`, `cantidad`,
  `subtotal`). Migration applied directly against the shared production
  Postgres instance also used by `panacea-backend` (Django) — coordinate
  timing so a concurrent `python manage.py makemigrations` in
  `panacea-backend` doesn't fight over the same table if Django's model
  layer there is ever extended to know about these columns/table.
  `panacea-backend` (Django) itself is not modified by this change.
- **Code**: `panacea-produccion-backend` — new SQLAlchemy model, Pydantic
  schemas, router endpoints, and service logic for the detalle resource; the
  existing (not-yet-implemented) `CuentaCorrienteProveedor` model/schema/
  router gain the new fields and nested payload handling.
- **Frontend**: `panacea-front` is unaffected unless/until it chooses to send
  `iva`/`percepcion`/`insumos` on `POST /ctacteprov` — the new fields are
  additive and optional, no existing payload shape breaks.
