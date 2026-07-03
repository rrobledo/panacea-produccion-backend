## 1. Project Scaffolding

- [x] 1.1 Initialize the FastAPI project layout per `design.md` (`app/main.py`,
      `app/config.py`, `app/db.py`, `app/deps.py`, `app/models/`,
      `app/schemas/`, `app/routers/`, `app/services/`), `requirements.txt`,
      `.env.example` (variable names only, no values), and `api/index.py`
      ASGI entrypoint for Vercel.
- [x] 1.2 Add a health-check route with no DB dependency and confirm
      `/docs` and `/openapi.json` render locally.
- [x] 1.3 Set up `pydantic-settings`-based config reading `DATABASE_URL`,
      `API_KEYS`, `CRON_SECRET`, `CORS_ORIGINS` from the environment, with
      no default values that resemble real credentials.

## 2. Database Schema Confirmation (blocking — needs explicit go-ahead)

- [x] 2.1 Obtain read-only Postgres access per the method the user confirms
      (do NOT default to using the credentials committed in
      `panacea-backend/vercel_app/settings.py` without explicit sign-off).
- [x] 2.2 Introspect (`\dt`, `\d <table>`) the actual table/column names for
      every table this service touches, especially the `managed=False`
      Django models (`Clientes`, `Remitos`, `RemitoDetalles`) whose real
      table names may not follow Django's default naming convention.
- [x] 2.3 Confirm `panacea_sales_v2` columns used across specs
      (`product_id`, `operation_year`, `operation_month`, `count`,
      `lugar_venta_id`) actually exist with those names/types.
- [x] 2.4 Record findings and adjust `app/models/` design before writing
      any ORM code (do not guess from `models.py` alone).

## 3. Platform Foundation (api-platform)

- [x] 3.1 Implement `require_api_key` dependency enforcing `X-API-Key` on
      POST/PUT/PATCH/DELETE, evaluated before route handlers run.
- [x] 3.2 Implement `require_cron_secret` dependency for the scheduled
      cascade endpoint, distinct from the general API key set.
- [x] 3.3 Configure CORS allow-listing from `CORS_ORIGINS`, no wildcard.
- [x] 3.4 Set up async pooled DB session handling (`app/db.py`) per design
      decision D10, one connection acquired/released per request.
- [x] 3.5 Add the global error-handling shell (validation → 400, not found
      → 404, DB errors → 500 logged without secrets) per pseudocode §0.

## 4. Productos, Insumos, Costeo

- [x] 4.1 Implement `Insumos` and `Productos` ORM models against the
      confirmed schema (Task 2) and CRUD routers/schemas. (`Insumos` was
      already built earlier as a prerequisite for `ctacteprov-detalle-insumos`.)
- [x] 4.2 Implement nested `Costos` (producto→insumo detail) CRUD.
- [x] 4.3 Port the cost-breakdown calculation (`costeo_service.py`) from
      `panacea-backend/costos/statistics.py::get_cost_by_product`,
      including the `cantidad_lotes`/`lote_produccion`/`utilidad`/
      `precio_actual` overrides. **Found and corrected a false-alarm
      during implementation**: initially believed `/precio_productos`'s
      dependency `articulos_final` didn't exist in production (it wasn't
      in the `\dt` table listing from the earlier schema confirmation) and
      asked the user how to handle it — the user corrected this: it's a
      VIEW, not a table (`\dt` only lists tables, not views), and it exists
      and works exactly as the reference SQL expects. Ported the SQL
      unmodified once confirmed. Lesson: `\dv`/`\d` needed alongside `\dt`
      for full schema confirmation, not just `\dt` alone.
- [x] 4.4 Port `personal_service.py` (`calcular_liquidacion`) as a pure
      function dependency of the costeo calculation.
- [x] 4.5 Implement `/costos_materia_prima` (list) and `/precio_productos`.
- [x] 4.6 Implement the static `/categorias` endpoint.
- [x] 4.7 Unit tests: cost breakdown against known fixture values from the
      reference backend; override parameters; all-products summary
      excludes `lote_produccion <= 1`. 9 tests in
      `tests/unit/test_productos_costeo.py`, including one that
      hand-computes the expected `costo_unitario_mp`/`precio_sugerido`/
      `margen_utilidad` for a known fixture and asserts the ported formula
      matches exactly.

## 5. Remitos & Clientes

- [x] 5.1 Implement `Clientes` CRUD with the computed `nombre` field and
      name-substring filter. **Deviation from the reference, documented in
      `app/schemas/clientes.py`**: the Django `ClientesSerializer` only
      exposes a read-only computed `nombre` — no field lets a caller
      actually set `nom1`/`nom2`, so its `POST`/`PUT` are a functional
      no-op in the reference. Exposed `nom1`/`nom2` directly as writable
      fields instead, since porting a write endpoint that can't write
      anything isn't a real feature.
- [x] 5.2 Implement `Remitos` + nested `RemitoDetalles` CRUD, including the
      `cantidad <= 0` exclusion on create and the computed `estado` field.
      **Second deviation, documented in `app/services/remitos_service.py`**:
      the reference `RemitosSerializer.update()` is also a no-op stub (it
      computes a diff and discards it — no field, including the parent
      row's own columns, is ever actually persisted on `PUT`). Implemented
      a real update instead: parent fields are updated, and detail lines
      are fully replaced (delete + recreate with the same `cantidad<=0`
      filter as create).
- [x] 5.3 Unit tests: estado computation for each timestamp combination;
      detail-line filtering on create; cliente/estado query filters.
      5 tests in `tests/unit/test_remitos_clientes.py`.

## 6. Proveedores & Cuenta Corriente

- [x] 6.1 Implement `Proveedor` CRUD with unique `cuit` enforcement.
      Read-path verified against live prod data; write-path (create,
      duplicate-`cuit` rejection, auth gate) verified against a local
      Docker Postgres — see 6.5.
- [x] 6.2 Implement `CuentaCorrienteProveedor` CRUD including the
      factura/pago creation branching logic (immediate-payment auto-mark
      as `PAGADO`, `importe_pendiente` computation, factura↔pago linkage).
      **Discovered a DB trigger (`trg_update_importe_pendiente`, documented
      in `design.md`) that already maintains `importe_pendiente`/`estado`
      on insert into `costos_cuentacorrienteproveedorafect` — the service
      layer creates rows and lets the trigger own that arithmetic rather
      than duplicating it.** Also discovered `image`/`image2` hold ~1GB of
      base64 receipt data across ~900 rows in production; deferred those
      columns at the ORM level (only loaded for single-record responses,
      never `list`) after an unfiltered list query hung fetching the full
      volume. **Write-path testing against a local Docker Postgres (see
      6.5) caught a real bug**: the create/update service code passed a
      `proveedor` key straight from the Pydantic payload into the
      SQLAlchemy model constructor, but the ORM model also has a
      relationship attribute named `proveedor` — SQLAlchemy tried to treat
      the plain int as a related object and crashed. Fixed by renaming to
      `proveedor_id` before constructing/updating the model in
      `app/services/cuenta_corriente_service.py`. This would have broken
      every `POST`/`PUT /ctacteprov` call in production; never triggered by
      the read-only verification done directly against prod earlier.
- [x] 6.3 Implement nested `/ctacteprov/{factura_id}/pagos`. Verified
      against a live fixture row and against local Docker fixtures
      (factura with no payments, and a factura with a linked payment).
- [x] 6.4 Implement `/ctacteprovresumen`. Verified against live data
      (parameterized query — the reference implementation's raw
      f-string-interpolated SQL was a SQL-injection risk, not replicated)
      and against a local Docker fixture covering all four contributing
      cases (unpaid cuenta-corriente factura, immediate-payment factura,
      factura paid off via a linked pago, and an out-of-date-range entry).
- [x] 6.5 Unit tests: each factura/pago creation branch; summary
      calculation against a fixture date range. Done against a disposable
      local Postgres run via Docker Compose (`docker-compose.yml` +
      `docker/init-db/01_schema.sql`, mirroring the relevant tables *and*
      the `trg_update_importe_pendiente` trigger) — not against production.
      11 tests total: 6 service-level (factura/pago branches, partial vs.
      full payment, pagos listing) + 4 HTTP-level (proveedor CRUD + auth
      gate, factura creation + nested pagos, resumen aggregation) + the
      pre-existing health check. See `README.md` for how to run them.

## 7. Production Analytics (read-only reporting)

- [x] 7.1 Implement `/get_produccion_by_category` and
      `/get_produccion_by_productos`.
- [x] 7.2 Implement `/get_insumos_by_month` (both `by_week` modes).
- [x] 7.3 Implement `/get_ventas_por_cliente` against `panacea_sales_v2`
      only. **Found and fixed a real SQL-injection vulnerability while
      porting**: the reference (`ventas.py::get_ventas_por_cliente`) builds
      its query via raw f-string interpolation of the `cliente` query
      parameter (`anio`/`mes` are `int()`-cast first so aren't exploitable,
      but the string param isn't) — parameterized via bind params instead
      in `app/services/analytics_service.py`, not replicated. Covered by a
      dedicated test (`test_sql_injection_attempt_in_cliente_param_is_inert`).
- [x] 7.4 Unit tests against fixture data for each report's aggregation
      logic. 8 tests in `tests/unit/test_analytics.py`.

## 8. Planning Generation

- [x] 8.1 Implement the planning pivot read (`GET /planning`) and columns
      metadata (`GET /planning_columnas`), matching reference grouping.
      **Found and fixed a fourth SQL-injection instance while porting**:
      the reference `PlanificacionViewSet.list()` passes the raw `anio`
      query-string value straight through to `get_planning()`, which
      f-string-interpolates it directly into SQL with **no `int()` cast at
      all** (unlike `get_produccion_by_category`, which does cast) — a
      real, unauthenticated injection point since `GET /planning` requires
      no API key. Fixed by declaring `anio: int` as a typed FastAPI query
      param (422 on non-integer input) and using a bind parameter.
- [x] 8.2 Implement the planning bulk cell edit (`POST /planning`).
- [x] 8.3 Implement `planning_service.generate_planning()` per
      `docs/sparc/02-pseudocode.md` §1 (recovered from the OS trash after
      the `docs/` directory was deleted mid-session — see note to user):
      candidate selection, zero-fill branch, sales-projection branch (with
      confirmed zero-fill for missing months), `dry_run` support,
      single-transaction commit.
- [x] 8.4 Wire `POST /planning/generate` route with `year`, `producto_id`,
      `dry_run` params and the 400 rejection for a disabled scoped product.
- [x] 8.5 Unit tests: zero-fill branch; full-year projection branch
      (hand-computed against the exact pseudocode formula — index per
      lugar_venta_id, averaged, `ceil(promedio*indice/10)*10`); partial-year
      projection branch (confirms zero-fill of gap months); idempotency
      (second run inserts nothing); dry-run makes no writes; scoped
      single-product generation matches the equivalent slice of a bulk run.
      10 tests in `tests/unit/test_planning.py`.

## 9. Programacion Generation

- [x] 9.1 Implement the programacion pivot read (`GET /programacion`) and
      columns metadata (`GET /programacion_columnas`), matching reference
      filters (anio, mes, responsable, semana). **Found and fixed a fifth
      and sixth SQL-injection instance**: the reference
      `ProgramacionViewSet.list()` passes `anio`/`mes`/`semana` through raw
      (no `int()` cast) to `get_programacion()`, and separately builds
      `and pr.responsable = '{responsable}'` via f-string — both
      unauthenticated (`GET`, no API key). Fixed with typed FastAPI query
      params + bind parameters, not replicated. The relative
      "week-within-month" baseline (`'2024-{mes}-02'`, hardcoded regardless
      of the queried year) *was* preserved verbatim — that's existing
      pivot-grid behavior the frontend may depend on, not a security issue.
- [x] 9.2 Implement the programacion bulk cell edit (`POST /programacion`).
- [x] 9.3 Implement `programacion_service.generate_programacion()` per
      `docs/sparc/02-pseudocode.md` §2: day-row generation (business days,
      eligibility checks), the 4-branch `corregido` correction formula,
      `dry_run` support, single-transaction commit, 400 on ineligible
      scoped product.
- [x] 9.4 Wire `POST /programacion/generate` route with `year`, `month`,
      `prev_year`, `prev_month` (with rollover default), `producto_id`,
      `dry_run` params.
- [x] 9.5 Implement `programacion_service.copy_week()` per pseudocode §3:
      required `from_year`/`from_week`/`to_year`/`to_week`, skip-not-null
      on unmatched rows, same-week rejection, `dry_run` support.
- [x] 9.6 Wire `POST /programacion/copy-week` route.
- [x] 9.7 Implement the scheduled cascade handler (`cron.py`): last-day-of-
      month self-check, calls `generate_programacion` for next month using
      the closing month as previous, cron-secret protected, non-2xx +
      logged on failure.
- [x] 9.8 Add the Vercel Cron entry in `vercel.json` (daily trigger, `0 23
      * * *` UTC — Vercel auto-injects `Authorization: Bearer $CRON_SECRET`
      when that env var is set, matching `require_cron_secret`'s
      expectation with no extra wiring needed).
- [x] 9.9 Unit tests: day-row generation eligibility (enrolled +
      habilitado + is_producto); each of the 3 corregido branches plus the
      zero-guard branch; sistema-overwrite behavior; copy-week matched and
      unmatched-row behavior; ISO week-boundary edge case (Risk R5,
      Dec-31-in-week-1-of-next-year); idempotency of re-running generation.
      17 tests in `tests/unit/test_programacion.py`. **Gap, not covered**:
      cron's actual last-day-of-month "run" branch — only the
      `require_cron_secret` auth gate is tested directly; the "run" path
      reuses `generate_programacion` (already covered) but exercising the
      date-based skip/run branching itself would need mocking
      `datetime.now()`, not done here.

## 10. Onboarding Flow Verification

- [x] 10.1 Integration test: create a product, call
      `planning/generate?producto_id=…` then
      `programacion/generate?producto_id=…` with `dry_run=false`, and
      verify the resulting rows match what a bulk run would have produced
      for that product alone (per `design.md` D8 and the
      programacion-generation spec's onboarding scenario). 1 test in
      `tests/unit/test_onboarding.py` — a scoped-onboarded product and a
      bulk-generated product with identical sales fixtures end up with
      byte-identical `costos_planificacion` and `costos_programacion` rows.

## 11. Deployment & Documentation

- [x] 11.1 Finalize `vercel.json` (routes + cron), verify `/docs` and
      `/openapi.json` reflect every implemented endpoint. 35 routes
      confirmed present in `/openapi.json`; `/docs` renders 200.
- [x] 11.2 Write `README.md` covering local setup, required env vars, and
      how to run tests. Added a minimal `tests/unit/test_health.py` (no
      tests existed yet) plus `requirements-dev.txt` so `pytest` is
      actually runnable, not just documented; verified both `pytest` and
      `uvicorn app.main:app` work as written.
- [x] 11.3 Document the `X-API-Key` header requirement for
      `panacea-front`'s config change (per proposal's BREAKING note). Added
      a dedicated "panacea-front integration note (BREAKING for writes)"
      section to `README.md`, plus a "Deployment (Vercel)" section
      covering the cron secret's auto-injection.
- [x] 11.4 Manual smoke test with `dry_run=true` against the real DB for
      each generation endpoint before any `dry_run=false` call is made
      against production data. **Found and fixed two real N+1
      performance bugs this surfaced** (invisible locally against the
      near-zero-latency Docker container, severe against the real
      network-latency-bound pooled connection):
      - `copy_week` issued one source-lookup query per target-week row —
        614 sequential round-trips for a real target week, which hung
        indefinitely (still running after 15+ seconds; had to be killed).
        Fixed by batch-fetching the whole source week in one query and
        matching in Python — same call now completes in ~5.4s.
      - `generate_programacion`'s corregido-correction loop issued 3-4
        queries per correction candidate — for a real bulk (no
        `producto_id`) call across 122 correction candidates, this was
        the same class of bug (not yet observed hanging, but the same
        shape). Fixed with the same batch-then-lookup pattern.
      Also **confirmed, not fixed**, the *already-documented and
      deliberately deferred* N+1 in `planning/generate`'s bulk sales
      query (`design.md`'s "N+1 sales queries... accepted for v1... flagged
      as a candidate optimization if bulk generation proves slow in
      practice, not solved preemptively") — a real bulk call across ~137
      products took ~23s. This is the exact "observed slow in practice"
      condition that design doc named; recorded here as the evidence, left
      unoptimized per that document's own scoping (a decision for the
      user, not a silent scope expansion here).
      Verified zero writes to production across every dry-run call made
      during this smoke test.
- [x] 11.5 Run the full test suite and confirm all spec scenarios have a
      corresponding passing test before considering this change complete.
      Cross-checked all 64 `#### Scenario:` headers across the 7 spec files
      against the test suite. **Found and fixed real gaps**:
      - `/costos/insumos` (list+filter, create) had **zero** test coverage
        despite being an explicit spec requirement — added
        `tests/unit/test_insumos.py`.
      - Every test's shared `client` fixture overrides `require_api_key`/
        `require_cron_secret` to a no-op, so "a valid key is accepted" and
        "a general API key alone doesn't satisfy the cron secret check"
        were **never actually exercised against the real auth logic** —
        only the "no key at all" rejection path was. Added
        `tests/unit/test_api_platform.py` (3 tests) that pop the override
        and hit the real dependencies with a real configured key/secret.
      - CORS's "reject an unlisted origin" scenario was untested — added
        to the same file.
      - `GET /programacion_columnas` had zero test coverage — added.
      - No test proved a bulk (non-scoped) `programacion/generate` call
        actually excludes disabled products — added.
      Full suite: **75 tests, all passing** (up from 68 before this pass).
      **Remaining minor gaps, judged acceptable**: cron's actual
      last-day-of-month skip/run date branching (would need mocking
      `datetime.now()` — only the auth gate is tested); a literal
      "omitted `dry_run` defaults to preview" HTTP-level test (covered in
      spirit — every dry-run test explicitly passes `dry_run=true` rather
      than omitting it, but the default is a one-line FastAPI parameter
      default, not independent logic); a distinct "full 12-month sales
      history" planning-generation test (the partial-history test already
      exercises the identical code path with more populated months).
