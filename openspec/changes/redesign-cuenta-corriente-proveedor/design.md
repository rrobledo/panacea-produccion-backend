## Context

`CuentaCorrienteProveedor` today does three jobs in one table: it's the
factura record, the pago record (`tipo_movimiento` discriminates), and the
implicit ledger (read by mixing both). Its `importe_pendiente`/`estado`
fields are kept correct by a DB trigger,
`trg_update_importe_pendiente` on `CuentaCorrienteProveedorAfect`
(AFTER INSERT/DELETE/UPDATE), which decrements/restores
`importe_pendiente` on both the `factura_id` and `pago_id` rows and
recomputes `estado`. `app/services/cuenta_corriente_service.py` is
explicit that this arithmetic must never be duplicated in application
code — the trigger owns it.

Constraints shaping every decision below:
- This service shares the **same production Postgres** as
  `panacea-backend` (Django, `managed=True` models over these exact
  tables). We're not touching Django code, but we are changing what gets
  written where.
- Data volume is small (~900 rows in `costos_cuentacorrienteproveedor`),
  which makes a real backfill migration (not just a schema change)
  tractable in one pass.
- `panacea-produccion` (the only frontend being cut over) has no
  global/cached state — each screen owns its own fetch — so the frontend
  side of the cutover is a bounded rewrite (~12 files), not a gradual
  migration.
- No object storage exists anywhere in the Panacea stack today;
  `CompraAdjunto` introduces the first one.

## Goals / Non-Goals

**Goals:**
- A normalized schema (`Compra`/`CompraDetalle`/`CompraImpuesto`/
  `CompraAdjunto`, `Pago`/`PagoMedio`/`PagoAplicacion`, `MovimientoCC`,
  `LibroIvaCompra`, `OrdenCompra`/`OrdenCompraDetalle`) that supports
  discriminated IVA/percepciones, multi-método payments, and purchase
  orders, per `proposal.md`.
- Preserve the proven "trigger owns cross-row balance arithmetic, app code
  never duplicates it" pattern, generalized to the new tables.
- A one-time, verifiable data migration for the ~900 existing rows, with
  historical tax-breakdown loss made explicit rather than fabricated.
- Attachments fully out of the database, in object storage.
- A cutover sequence with a real rollback window, not an instantaneous
  simultaneous flip.

**Non-Goals** (carried from `proposal.md`, restated for implementation
clarity):
- No accounting/asiento generation logic — `centro_costo_id`/
  `cuenta_contable_id` are reserved nullable FKs only.
- No multi-currency (`moneda`/`cotizacion`) fields.
- No goods-receipt/stock module beyond `OrdenCompra`'s own
  `cantidad_recibida` counter.
- No `DROP TABLE` on the legacy schema, ever, in this change.
- No changes to `panacea-backend` Django code.
- No dual-write / gradual per-screen rollout — a single sequenced cutover
  (see Migration Plan).

## Decisions

**D1 — Two distinct "saldo" concepts, not one.** `Compra.saldo_pendiente`
is a trigger-maintained, denormalized column (direct generalization of
today's `importe_pendiente`) — needed because the Pagos/Facturas
Pendientes screens must filter "which facturas still owe money" cheaply,
on every list request. The **proveedor-level Cuenta Corriente balance**
stays fully derived: a window-function sum (`SUM(haber - debe) OVER (...)`
ordered by `fecha, id`) over `MovimientoCC`, never stored, matching the
ERP spec's explicit principle ("el saldo siempre se calcula").
*Alternative considered*: store only the ledger and derive
`saldo_pendiente` per compra from it on every read — rejected, too slow
for the pending-invoices list which is queried far more often than the
full ledger is walked.

**D2 — `MovimientoCC` rows are appended by application code at
`Compra`/`Pago` creation time, in the same transaction; `PagoAplicacion`'s
effect on `Compra.saldo_pendiente` stays trigger-owned.** The ledger needs
a human-readable `documento` label and a `tipo` (FACTURA/PAGO/NC/ND) that
are naturally known in the service layer at creation time; the
cross-row balance decrement is exactly the kind of "must never be
double-applied" arithmetic the existing trigger pattern already proves out
for `Afect`. `PagoAplicacion` is a direct rename/generalization of
`CuentaCorrienteProveedorAfect` — same shape, same trigger strategy,
now decrementing `Compra.saldo_pendiente` instead of
`CuentaCorrienteProveedor.importe_pendiente`.
*Alternative considered*: trigger-populate `MovimientoCC` directly off
`Compra`/`Pago` inserts — rejected, would push NC/ND sign-convention
business logic into SQL where it's harder to test in isolation (mirrors
the existing `services/` layer rationale from `produccion-costos-api`).

**D3 — `CompraImpuesto` is fully generic** (`tipo`, `base_imponible`,
`porcentaje`, `importe`), not separate typed tables per IVA/Percepción/
Retención. `tipo` is a string validated against a fixed vocabulary
(`IVA_21`, `IVA_10_5`, `IVA_27`, `PERCEPCION_IVA`, `PERCEPCION_IIBB`,
`PERCEPCION_MUNICIPAL`, `RETENCION_IVA`, `RETENCION_GANANCIAS`,
`RETENCION_SUSS`, `IMPUESTOS_INTERNOS`, `HISTORICO_SIN_DESGLOSE`) at the
Pydantic/service layer, not a DB constraint — so a new tax type is a
vocabulary addition, not a migration. `LibroIvaCompra` pivots these into
report columns only at read time.
*Alternative considered*: separate `CompraIva`/`CompraPercepcion`/
`CompraRetencion` tables — rejected, directly contradicts the source
spec's own stated principle and would need a migration for every new tax
type.

**D4 — `PagoMedio` banking fields (`banco`, `numero`,
`fecha_acreditacion`) are nullable at the DB level, required only when
`tipo` is `CHEQUE`/`ECHEQ`, enforced in the Pydantic schema.** Mirrors how
`INMEDIATE_PAYMENT_TIPOS_PAGO`-conditional logic already works in
`cuenta_corriente_service.py` today — conditional-on-value validation
belongs in the service/schema layer, not as DB CHECK constraints.

**D5 — Historical `iva`/`percepcion` totals migrate to a single
`CompraImpuesto` row per compra, `tipo=HISTORICO_SIN_DESGLOSE`.** The
original alícuota/tipo split was never captured in the source data and
cannot be reconstructed; fabricating a plausible-looking split (e.g.
assuming 21%) would make `LibroIvaCompra` silently lie about pre-cutover
periods. Explicit unknown beats invented precision.

**D6 — Cutover is sequenced, not instantaneous.** New tables + new
endpoints ship first (additive, old endpoints still live and are what
`panacea-produccion` still calls). The data-migration script runs next,
against production, in a short window. Only after migrated data is
verified does `panacea-produccion` deploy against the new endpoints, at
which point the legacy `/costos/ctacteprov*` routes are removed from
routing (return 404) — old tables stop receiving writes from that moment,
but are not dropped.
*Alternative considered*: a truly simultaneous flip (deploy backend +
frontend + retire old code at the same instant) — rejected, leaves no
rollback window if the frontend cutover surfaces a modeling gap; keeping
old tables/read-paths alive costs little and buys a real revert option
(re-point routing, redeploy previous frontend build).

**D7 — Attachment migration to object storage runs once, as part of the
data-migration step, not lazily on first read.** Each legacy `image`/
`image2` base64 blob is decoded and uploaded to Vercel Blob during the
backfill; the resulting URL becomes a `CompraAdjunto` row. No legacy row
is left half-migrated indefinitely.

**D8 — `OrdenCompra` reception is application-level, not trigger-based.**
Creating a `Compra` with `orden_compra_id` set increments the matching
`OrdenCompraDetalle.cantidad_recibida` and advances `OrdenCompra.estado`
in the same service call. Reception-matching logic (which line, how much)
is easier to express and test as Python than as SQL, and this path has no
proven trigger precedent to reuse (unlike D1/D2).

**D9 — `CompraDetalle` rows are one of three mutually-exclusive
references (`tipo=INSUMO`/`ITEM_GASTO`/`LIBRE`), not a single polymorphic
FK.** Extends the pattern `OrdenCompraDetalle` already uses (optional
`insumo_id` alongside a free-text `descripcion`) with a second concrete
catalog, `ItemGasto` (`codigo`/`nombre`/`activo` only — no `precio`/
`cantidad`, since expense concepts aren't costeo inputs the way `Insumo`
rows are). `tipo` plus which FK is populated is validated at the Pydantic
layer (mirrors D3/D4's house style of app-level over DB-level validation),
not a DB CHECK constraint. `descripcion` is never left null: for
`INSUMO`/`ITEM_GASTO` the service snapshots the referenced catalog row's
`nombre` at creation time if the client didn't override it, so a later
rename of the catalog entry doesn't retroactively change a historical
compra's line label, and downstream consumers (Órdenes de Compra reception
matching, Libro IVA display, any print/PDF view) never need to branch on
`tipo` just to render a line.
*Alternative considered*: a single nullable `referencia_id` +
`referencia_tipo` polymorphic pair — rejected, Postgres can't enforce a
polymorphic FK's referential integrity, and two concrete nullable FKs cost
nothing at this data volume.

## Risks / Trade-offs

- **[Risk] Two "saldo" concepts (D1) could confuse future maintainers** →
  *Mitigation*: document the distinction in both models' docstrings/code
  comments and in the `cuenta-corriente-proveedor` spec; add an
  integration test asserting `Compra.saldo_pendiente` and the
  `MovimientoCC`-derived balance agree at any point in time for a given
  proveedor.
- **[Risk] Sequenced (not atomic) cutover leaves a window where legacy
  endpoints are technically still reachable** → *Mitigation*: legacy
  routes are removed from the router (not just left unused) at the same
  deploy as the frontend cutover, not on a separate later timeline —
  there's no in-between state where both are simultaneously "live and
  intended to be used."
- **[Risk] `CompraImpuesto.tipo` as a free string risks typos fragmenting
  the Libro IVA pivot** (`"IVA_21"` vs `"IVA21"`) → *Mitigation*: validate
  against the fixed vocabulary (D3) at the API boundary; reject unknown
  values rather than silently storing them.
- **[Risk] Object storage is a new external dependency and failure mode**
  → *Mitigation*: `CompraAdjunto` upload is a distinct step after `Compra`
  creation succeeds; a failed upload doesn't roll back the `Compra`, it
  just leaves that attachment retryable.
- **[Trade-off] `LibroIvaCompra` is derived, not materialized, for v1** →
  accepted at current volume (~900 rows, growing slowly); flagged as a
  candidate for materialization if report load increases, not solved
  preemptively.
- **[Trade-off] `OrdenCompra` reception has no over-delivery tolerance or
  unit-conversion logic** → accepted, consistent with the "no separate
  goods-receipt module" non-goal; revisit only if real usage demands it.

## Migration Plan

1. Ship new tables (`Compra`, `CompraDetalle`, `CompraImpuesto`,
   `CompraAdjunto`, `Pago`, `PagoMedio`, `PagoAplicacion`, `MovimientoCC`,
   `OrdenCompra`, `OrdenCompraDetalle`) and extended `Proveedor` columns
   via a new numbered SQL migration (mirrored into `docker/init-db/`,
   following the `migrations/0001_*` precedent), including the
   generalized trigger (`PagoAplicacion` → `Compra.saldo_pendiente`,
   modeled directly on `trg_update_importe_pendiente`).
2. Ship new service/schema/router code behind new route prefixes
   (`/costos/compras`, `/costos/pagos`, `/costos/ordenes-compra`,
   `/costos/cuenta-corriente`, `/costos/libro-iva-compras`), deployed but
   not yet linked from `panacea-produccion`. Legacy `/costos/ctacteprov*`
   stays live and authoritative during this step.
3. Run the one-time data-migration script against production in a short
   window: backfill `Compra`/`Pago`/`PagoAplicacion`/`MovimientoCC` from
   the ~900 legacy rows (tagging historical tax rows
   `HISTORICO_SIN_DESGLOSE`, D5), and migrate base64 images to Vercel Blob
   + `CompraAdjunto` (D7).
4. Verify: row-count parity between legacy and new tables, and spot-check
   that `Compra.saldo_pendiente` agrees with the legacy
   `importe_pendiente` it was derived from, before touching the frontend.
5. Deploy `panacea-produccion` against the new endpoints; remove routing
   to legacy `/costos/ctacteprov*` in the same release (D6).
6. Retain legacy tables, read-only, as historical archive (no writes, no
   drop) — `panacea-backend`'s `managed=True` models over them keep
   working for any legacy read/admin use, indefinitely until a future,
   separate decision to remove them.
7. **Rollback**: since legacy tables/endpoints are never dropped in this
   plan, reverting is re-enabling the legacy routes and redeploying the
   previous `panacea-produccion` build — no destructive step needs
   undoing.

## Open Questions

- Retention period for the legacy tables before actual removal (one
  fiscal year? indefinite?) — deferred to a future decision once the new
  model has run in production for a while.
- Whether `CompraImpuesto.tipo`'s vocabulary should eventually move to a
  configuration table (matching the source spec's "tipos... no deben
  estar codificados" principle) rather than an app-validated string —
  deferred; nothing depends on this being a string vs FK today, so it's a
  low-cost future upgrade.
- Final confirmation that Vercel Blob (vs. S3/Cloudinary) is the object
  storage choice — recommended during discovery for its zero-extra-account
  fit with the existing Vercel deployment, not yet a hard commitment.
- Whether `OrdenCompra` needs an over-delivery tolerance policy — deferred
  until real usage surfaces the need.
