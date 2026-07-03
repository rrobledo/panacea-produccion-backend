## Context

`panacea-backend` (Django + DRF, Vercel, Postgres) currently owns this
domain. Its costing/CRUD endpoints are straightforward, but four business
processes — annual planning generation, monthly schedule generation +
correction, weekly schedule copy, and new-product onboarding — are run by
hand today via SQL scripts with hardcoded years/months/weeks
(`costos/produccion.py` documents the *read* side of planning/programacion;
the *generation* SQL itself lives outside the codebase, in ad-hoc scripts
the user runs manually). This new service both ports the existing REST
surface (for frontend compatibility) and turns those four manual scripts
into parametrized, idempotent REST endpoints.

Two things shape every decision below: (1) this service will be developed
and tested directly against the **same production Postgres instance**
`panacea-backend` uses — there is no disposable dev database — and (2) some
of the reference SQL, once actually parsed, contained real bugs (a stray
`end` keyword) and unintended-looking behavior (destructive NULL-out on
no-match, partial-year gaps) that were resolved as explicit product
decisions rather than replicated literally. See `specs/*/spec.md` for the
resulting normative behavior.

## Goals / Non-Goals

**Goals:**
- Full-parity REST contract (paths + payloads) for the core costing domain,
  so `panacea-front` works against this service unmodified except for a new
  auth header on writes.
- Turn the four manual SQL processes into parametrized, idempotent,
  dry-run-capable REST endpoints.
- Auto-generated, always-current OpenAPI docs (FastAPI native).
- No secrets in source; API-key auth on writes; a narrower cron-secret
  control on the scheduled bulk-mutation endpoint.

**Non-Goals:**
- Reimplementing the legacy POS-schema analytics endpoints (product
  history/cronograma) — deferred, data-source currency unconfirmed.
- Any database schema migration or DDL change — this service reads/writes
  the existing tables as-is.
- Decommissioning or modifying `panacea-backend` — it keeps running.
- Frontend changes beyond documenting the new required auth header.

## Decisions

**D1 — FastAPI + Pydantic schemas mirroring the DRF serializer field names.**
Satisfies the "same contract" goal without hand-maintained OpenAPI docs:
FastAPI derives `/docs` and `/openapi.json` from the same models used for
request/response validation.
*Alternative considered*: Django + DRF (closest to the reference, less
migration risk) — rejected because the technical requirement is explicitly
FastAPI.

**D2 — `services/` layer separate from `routers/`.**
Routers stay thin (parse, validate, call one service function, shape the
response); business logic — especially the four generation processes —
lives in unit-testable service functions with no HTTP or ORM-session
coupling beyond an injected connection. This is what makes Phase 4-style
build-test-fix loops fast for the riskiest code in the project.
*Alternative considered*: logic inline in route handlers, like
`produccion.py` does today — rejected; harder to unit test the generation
formulas in isolation from FastAPI request/response machinery.

**D3 — `dry_run` defaults to `true` on every generation/mutation endpoint
that isn't simple single-row CRUD** (`planning/generate`,
`programacion/generate`, `programacion/copy-week`). The caller must
explicitly pass `dry_run=false` to commit. Direct mitigation for developing
against the live production database: makes accidental bulk mutation
require a deliberate second decision, not just a request the client fires
by default.
*Alternative considered*: standing up a separate staging DB before writing
any generation code — the user chose to work directly against production;
`dry_run` is the compensating control given that choice.

**D4 — Idempotency via existence checks, matching the source SQL's
`NOT EXISTS` guards.** Every generation endpoint is safe to call repeatedly:
it only inserts rows that don't already exist and only updates rows it can
positively identify (by `producto_id` + `fecha`). No endpoint does a
blanket delete-and-regenerate.

**D5 — Two generation branches selected per-product, not per-batch, in
`planning/generate`.** A product with prior-year sales data uses the
sales-projection formula; a product without uses zero-fill. This mirrors
the user's stated rule ("in case we have information about the previous
year") applied product-by-product within a single bulk call, rather than
requiring the caller to choose a branch up front.

**D6 — Sales-projection branch zero-fills months missing prior-year data**
(confirmed decision, deviates from a literal port of the reference SQL,
which would simply omit those months). Every product ends up with exactly
12 planning rows per year, which the pivot read endpoint (`GET /planning`)
and downstream reporting already assume.

**D7 — `programacion/copy-week` skips (does not null) target rows with no
source-week match** (confirmed decision, deviates from the reference SQL's
literal UPDATE...NULL behavior). Copying a week is additive/corrective, not
destructive by default.

**D8 — Product onboarding is a documented call sequence, not a new
endpoint.** `POST /productos` → `planning/generate(producto_id=…)` →
`programacion/generate(producto_id=…)`. Reuses the bulk generation logic
scoped by an optional `producto_id` parameter instead of a parallel
single-product code path (see `planning-generation`/`programacion-generation`
specs).

**D9 — The scheduled monthly cascade authenticates via a distinct
cron-secret, not the general API key.** The cascade is a bulk,
all-products mutation; if it accepted the same key the frontend holds, a
leaked frontend key could trigger unscheduled bulk mutations. The cron
handler itself still self-checks "is today the last day of the month"
since neither Vercel plan tier offers that as a native schedule primitive.

**D10 — Async DB access via a pooled connection string** (Neon/Vercel
Postgres `-pooler` endpoint), one connection acquired per request. Required
by Vercel's stateless/cold-start serverless model — a process-local
connection pool doesn't survive between invocations.

## Risks / Trade-offs

- **[Risk] Developing directly against production Postgres** → *Mitigation*:
  `dry_run=true` default (D3) + idempotent existence checks (D4) + each
  generation call wrapped in a single transaction (all-or-nothing commit).
- **[Risk] Table/column names for `managed=False` Django models
  (`Clientes`, `Remitos`, `RemitoDetalles`) may not match Django's naming
  convention** → *Mitigation*: read-only schema introspection
  (`\dt` / `\d <table>`) against the live DB is the first implementation
  task, before any ORM model is written; models are written from observed
  reality, not from `models.py` assumptions.
- **[Risk] Adding a required `X-API-Key` header is a contract break for
  `panacea-front`**, which sends no auth today → *Mitigation*: called out
  explicitly as the one approved exception to "same contract"; frontend
  config change is a known, tracked follow-up, not a surprise.
- **[Risk] ISO week-number edge cases at year boundaries** in
  `programacion/copy-week` (Dec 31 can fall in ISO week 1 of the next year)
  → *Mitigation*: explicit edge-case tests around year boundaries before
  this endpoint ships.
- **[Trade-off] N+1 sales queries in `planning/generate`'s bulk path** (one
  `panacea_sales_v2` query per candidate product) → accepted for v1 for
  simplicity/correctness; flagged as a candidate optimization (single
  batched query) if bulk generation proves slow in practice, not solved
  preemptively.

## Migration Plan

1. Stand up the FastAPI skeleton (D1/D2) with health check + OpenAPI docs,
   no DB-dependent routes yet.
2. Read-only schema introspection against the live DB (mitigates the
   table-naming risk above) before writing any ORM model.
3. Port CRUD capabilities one at a time (`productos-insumos-costeo` →
   `remitos-clientes` → `proveedores-cuenta-corriente`), each independently
   verifiable against the existing Django backend's responses for the same
   query.
4. Implement `planning-generation` and `programacion-generation` behind
   `dry_run=true` default; validate generated rows against what the manual
   SQL would have produced for a known fixture product/year/month before
   ever calling with `dry_run=false`.
5. Wire the Vercel Cron entry for the monthly cascade last, once the
   on-demand endpoint is verified.
6. No rollback of `panacea-backend` is required at any point — this service
   is additive. Rollback of this service itself is "stop routing traffic to
   it" / redeploy previous Vercel deployment; no destructive DB changes are
   made by any endpoint (only inserts and targeted updates, never deletes,
   in the generation endpoints).

## Open Questions

- Exact table/column names for `managed=False` models — resolved by
  introspection (Migration Plan step 2), not assumed here.
- Vercel cron-secret env var delivery mechanism for this specific account's
  plan/configuration — resolved during `api-platform` implementation.
- Whether the N+1 sales-query pattern in bulk `planning/generate` needs
  optimization — deferred until observed in practice.

## Schema Introspection Findings (2026-07-02)

Read-only introspection (`\dt`, `\d <table>`, `pg_get_functiondef`) against
the live shared Postgres instance, per the Migration Plan/Risk mitigation
above.

- **All `managed=True` Django tables match `models.py` exactly**, column for
  column: `costos_insumos`, `costos_productos`, `costos_productosref`,
  `costos_costos`, `costos_proveedor`, `costos_cuentacorrienteproveedor`,
  `costos_cuentacorrienteproveedorafect`, `costos_planificacion`,
  `costos_programacion`, `planificacion2024`.
- **`managed=False` table names confirmed**: `clientes` (bare, matches its
  explicit `db_table`), and — importantly — `costos_remitos` /
  `costos_remitodetalles` (Django's `costos_` app-label prefix still applies
  even without an explicit `Meta.db_table`, contrary to what one might guess
  for a `managed=False` model). `clientes` itself has many more columns than
  `models.py` exposes (full legacy customer record: `cc_saldoacuenta`,
  `idprovincia`, `fechaultcompra`, etc.) — only map the fields this service
  actually needs (`idcliente`, `nom1`, `nom2`), ignore the rest.
- **`panacea_sales_v2` columns confirmed**, including all five referenced in
  specs (`product_id`, `operation_year`, `operation_month`, `count`,
  `lugar_venta_id`) plus additional columns not currently used by any spec
  (`subtotal`, `category`, `customer`, `week_of_month`, `day_of_week_text`,
  etc.) — available if a future capability needs them, not mapped now.
- **[Important, changes D-level behavior] `costos_cuentacorrienteproveedor`
  has an `AFTER INSERT OR DELETE OR UPDATE` trigger,
  `trg_update_importe_pendiente` → `update_importe_pendiente()`, on
  `costos_cuentacorrienteproveedorafect`.** On every insert of an `afect`
  row (payment↔factura linkage), the trigger decrements
  `importe_pendiente` on **both** the `factura_id` and `pago_id` rows by
  `NEW.importe`, then recomputes `estado` (`PAGADO` if
  `importe_pendiente <= 0`, else `PENDIENTE`) for both rows. Delete/update
  reverse or re-apply symmetrically. **Consequence for this service's
  `CuentaCorrienteProveedor`/pago implementation (§6.2 in `tasks.md`)**: the
  service must NOT re-implement this balance/estado math in
  `services/`/application code — it only needs to (a) create the factura
  row with `importe_pendiente = importe_total` initially, (b) create the
  pago row with `importe_pendiente = importe_total` initially (matching the
  reference Django serializer), and (c) insert the
  `CuentaCorrienteProveedorAfect` linkage row — the trigger then owns
  updating both rows' `importe_pendiente`/`estado` as a side effect of that
  insert. Duplicating the arithmetic in application code would double-apply
  it. This must be covered by an integration-style test (insert the afect
  row for real against a fixture pair of rows, assert the trigger's
  resulting state), not just a unit test that mocks the DB.
- **[Caution, do not use] Five English-named tables with real row counts
  exist alongside the Spanish-named ones this service targets**:
  `costos_products` (75 rows), `costos_supplies` (83 rows), `costos_costs`
  (74 rows), `costos_costsdetails` (654 rows), `costos_compras` (0 rows).
  None of these are referenced by `panacea-backend/costos/models.py` — they
  appear to be a legacy/parallel schema (possibly an abandoned
  rename/migration attempt) and are **not** the tables backing
  `/productos`, `/insumos`, `/costos`, or `/proveedores`/`/ctacteprov`.
  Flagged here so no future task accidentally binds an ORM model to the
  English-named table by name-similarity.
