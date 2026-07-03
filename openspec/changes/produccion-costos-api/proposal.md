## Why

Panacea's production/costing back office (`panacea-backend`) is a Django
monolith on Vercel/Postgres where four core business processes — annual
sales planning, monthly production scheduling, month-over-month plan
correction, and weekly schedule duplication — are executed by hand via
one-off SQL scripts with hardcoded years/months/weeks. This is error-prone
(a forgotten hardcoded year silently inserts wrong data), not repeatable on
demand, not auditable, and blocks onboarding a new product without someone
re-running SQL by hand. We need a documented, parametrized REST API that
replaces the manual scripts with idempotent, on-demand (and where
appropriate, scheduled) operations, while keeping the existing costing
domain (productos, insumos, costeo, remitos, proveedores) available through
a compatible contract for the current frontend.

## What Changes

- New service `panacea-produccion-backend`: Python + FastAPI, deployed on
  Vercel, same Postgres instance/schema as `panacea-backend`, with
  auto-generated OpenAPI/Swagger documentation.
- Port the core costing domain from `panacea-backend` with **identical URL
  paths and payload shapes** so `panacea-front` keeps working unmodified for
  ported endpoints: insumos, productos, costos (per-product insumo detail),
  remitos + detail, clientes, proveedores, cuenta corriente proveedor +
  pagos, the planning/programacion pivot read+bulk-edit endpoints, and the
  read-only cost/production reporting endpoints.
- **New** parametrized, idempotent endpoints replacing the four manual SQL
  processes:
  - `POST /planning/generate` — annual planning row generation (zero-fill or
    prior-year-sales projection, chosen per product), for all enabled
    products or scoped to one (`producto_id`), replacing the two hand-run
    INSERT queries.
  - `POST /programacion/generate` — monthly schedule day-row generation plus
    the month-over-month `corregido` correction, for all products or scoped
    to one, replacing the manual INSERT + UPDATE pair. Also wired to a daily
    Vercel Cron job that runs the cascade automatically on the last day of
    each month.
  - `POST /programacion/copy-week` — copies a week's planned quantities to
    another week matched by day-of-week, replacing the hardcoded weekly
    UPDATE.
- Product onboarding cascade: creating a product does not auto-enroll it;
  calling `planning/generate` and `programacion/generate` with that
  product's id performs the same generation "just for that one product" —
  no separate code path needed.
- **BREAKING (new requirement, not a regression)**: mutating endpoints
  (POST/PUT/PATCH/DELETE) require an `X-API-Key` header. The reference
  backend has no auth at all; `panacea-front` will need a small config
  change to send the key. Read (GET) endpoints stay open.
- All environment-sensitive values (DB connection string, API key(s), cron
  secret) come from Vercel environment variables — never committed to
  source (the reference backend currently commits a plaintext DB password).
- **Deferred, not in this change**: the legacy analytics endpoints that
  query a separate/older POS schema (`documentos`/`articulos`/`categorias`)
  with hardcoded years and dead code (product history, product cronograma,
  cronograma-by-week-of-month) — their data source currency is unconfirmed.

## Capabilities

### New Capabilities

- `productos-insumos-costeo`: CRUD for insumos and productos, per-product
  insumo cost detail (costos), cost-breakdown and suggested-price
  calculations (`/costos_materia_prima`, `/precio_productos`), and the
  static categories list.
- `planning-generation`: the planning pivot read/bulk-edit endpoints
  (`/planning`, `/planning_columnas`) plus the new `POST /planning/generate`
  annual generation endpoint (zero-fill and sales-projection branches).
- `programacion-generation`: the schedule pivot read/bulk-edit endpoints
  (`/programacion`, `/programacion_columnas`), the new
  `POST /programacion/generate` (day-row generation + `corregido`
  correction, on-demand and via monthly cron), and
  `POST /programacion/copy-week`.
- `remitos-clientes`: CRUD for clientes and remitos (with nested delivery
  detail lines).
- `proveedores-cuenta-corriente`: CRUD for proveedores, their cuenta
  corriente entries and payments, and the account summary endpoint.
- `produccion-analytics`: read-only aggregate reporting endpoints —
  production by category/product, insumos-by-month usage, and sales-by-client.
- `api-platform`: cross-cutting FastAPI app concerns — API-key auth on
  writes, a separate cron-secret control on the scheduled cascade endpoint,
  CORS allow-listing, environment-based configuration, and the Vercel
  deployment/cron wiring that every other capability depends on.

### Modified Capabilities

None — this is a new service; there are no existing specs in this repo yet.

## Impact

- **New code**: entire `panacea-produccion-backend` FastAPI application
  (routers, services, ORM models, Pydantic schemas, tests) — see
  `design.md`.
- **Database**: shared production Postgres instance with `panacea-backend`
  (`costos_productos`, `costos_insumos`, `costos_costos`,
  `costos_planificacion`, `costos_programacion`, `costos_remitos` and
  related tables, plus the externally-populated, read-only
  `panacea_sales_v2`). No schema migrations from this service in this
  change — read/write against the existing schema only.
- **Frontend**: `panacea-front` needs a config change to send the new
  `X-API-Key` header on writes once this service is fronted for those
  routes; no other contract changes for ported endpoints.
- **Deployment**: new Vercel project, environment variables for DB
  connection string, API key(s), and cron secret; a Vercel Cron entry for
  the monthly programacion cascade (requires Pro tier or higher).
- **Existing system**: `panacea-backend` is not modified or decommissioned
  by this change; it keeps running. Cutover is a future decision.
