## 1. Database Migration

- [x] 1.1 Write `migrations/0001_ctacteprov_detalle_and_iva.sql`: add
      `iva`/`percepcion` (`DOUBLE PRECISION DEFAULT 0`) to
      `costos_cuentacorrienteproveedor` and create
      `costos_cuentacorrienteproveedordetalle` (FKs to
      `costos_cuentacorrienteproveedor` `ON DELETE CASCADE` and
      `costos_insumos` `ON DELETE RESTRICT`, `cantidad`, `subtotal`), all
      with `IF NOT EXISTS` guards so it's safe to re-run. Also mirrored into
      `docker/init-db/02_ctacteprov_detalle_and_iva.sql` and applied to the
      local Docker Postgres — verified column/table/FK/cascade definitions
      match the design exactly.
- [x] 1.2 Add an index on
      `costos_cuentacorrienteproveedordetalle.cuentacorrienteproveedor_id`.
- [x] 1.3 Dry-run the script inside `BEGIN; ...; ROLLBACK;` against the
      shared Postgres instance; confirm no errors and inspect the resulting
      column/constraint definitions before committing. Clean — no errors,
      only a cosmetic Postgres NOTICE that the index name was truncated to
      fit the 63-byte identifier limit (functionally irrelevant).
- [x] 1.4 Apply the migration for real; verify with
      `\d costos_cuentacorrienteproveedor` and
      `\d costos_cuentacorrienteproveedordetalle` that columns, FKs, and
      cascade behavior match the design. Applied 2026-07-02. Verified: both
      new columns default to `0` on all existing rows (sampled), the new
      table exists empty with the correct FKs/cascade behavior, no existing
      data was altered.

## 2. Models & Schemas

- [x] 2.1 Add `iva`/`percepcion` fields to the `CuentaCorrienteProveedor`
      SQLAlchemy model and its Pydantic request/response schemas (create +
      read), defaulting to `0` when omitted. (List response includes them
      too — unlike images, two floats are cheap enough to always return.)
- [x] 2.2 Add a new `CuentaCorrienteProveedorDetalle` SQLAlchemy model
      (`costos_cuentacorrienteproveedordetalle`) with `insumo_id`,
      `cuentacorrienteproveedor_id`, `cantidad`, `subtotal`, and a
      relationship back to `CuentaCorrienteProveedor`.
- [x] 2.3 Add Pydantic schemas for the detalle resource: create payload
      (`insumo`, `cantidad`, `subtotal`), read payload (adds `id`).
- [x] 2.4 Add an `insumos: list[DetalleRead]` field to the
      `CuentaCorrienteProveedor` read schema, and an optional
      `insumos: list[DetalleCreate] | None` field to its create schema.
      (Scoped `insumos` to the detail schema only, not the list schema —
      same reasoning as deferring images: a one-to-many join fan-out on
      every row of an unpaginated 1200+-row list isn't worth it when
      nothing in the spec requires it there.)

## 3. Cuenta Corriente Endpoints (extend existing CRUD)

- [x] 3.1 Update the `POST /ctacteprov` service function to accept
      `iva`/`percepcion` and persist them alongside `importe_total`.
- [x] 3.2 Update the `POST /ctacteprov` service function to accept an
      optional `insumos` array and create one
      `CuentaCorrienteProveedorDetalle` row per item, linked to the newly
      created entry, in the same DB transaction as the parent insert.
      **Found and fixed another real bug via local Docker testing**: the
      same `proveedor`/`proveedor_id` collision documented in
      `produccion-costos-api/tasks.md` §6.2 would have recurred for
      `insumo`/`insumo_id` had the detalle schema's field been passed
      straight into the model constructor — avoided by mapping
      `insumo` → `insumo_id` explicitly in the service layer from the start.
      Separately, a real bug *was* hit and fixed: returning an
      already-in-session object after a trigger-driven UPDATE (via the
      `costos_cuentacorrienteproveedorafect` insert) silently returned
      stale pre-trigger values from SQLAlchemy's identity map; fixed with
      `execution_options(populate_existing=True)` on the reload query in
      `get_cuenta_corriente`.
- [x] 3.3 Update the `GET /ctacteprov/{id}` (and list, if applicable)
      response to include the entry's `insumos` detail rows. (List
      endpoint intentionally excluded — see 2.4 note.)

## 4. Insumo Detail Endpoints (new nested resource)

- [x] 4.1 Implement `GET /ctacteprov/{id}/insumos` — list detail rows for
      one entry, ordered by `id`; 404 if `{id}` doesn't exist.
- [x] 4.2 Implement `POST /ctacteprov/{id}/insumos` — accept a single object
      or array of `{insumo, cantidad, subtotal}` and create one row per
      item, linked to `{id}`; 404 if `{id}` doesn't exist.
- [x] 4.3 Implement `DELETE /ctacteprov/{id}/insumos/{detalle_id}` — delete
      one detail row; 404 if it doesn't exist or doesn't belong to `{id}`.
- [x] 4.4 Wire all three routes into the router module for this domain
      (`app/routers/cuenta_corriente.py`), behind the existing
      `require_api_key` dependency for the mutating ones.

## 5. Tests

- [x] 5.1 Unit test: `POST /ctacteprov` with `iva`/`percepcion` persists
      both fields; omitting them defaults to `0`.
- [x] 5.2 Unit test: `POST /ctacteprov` with a nested `insumos` array
      creates the parent and all detail rows in one transaction.
- [x] 5.3 Unit test: `GET /ctacteprov/{id}` includes the `insumos` array.
- [x] 5.4 Unit test: `GET /ctacteprov/{id}/insumos` lists only rows for that
      entry.
- [x] 5.5 Unit test: `POST /ctacteprov/{id}/insumos` with a single object
      and with an array both create the expected row(s); 404 for an unknown
      `{id}`.
- [x] 5.6 Unit test: `DELETE /ctacteprov/{id}/insumos/{detalle_id}` removes
      only the targeted row; 404 for a mismatched `{id}`/`{detalle_id}` pair.
- [x] 5.7 Unit test: deleting a `CuentaCorrienteProveedor` entry cascades to
      delete its detail rows.

All 7 tests written in `tests/unit/test_ctacteprov_detalle_insumos.py`,
run against the local Docker Postgres (see `README.md`). Full suite
(18 tests across this change and the parent `produccion-costos-api`
change) passes together.

## 6. Verification

- [x] 6.1 Confirm `panacea-front`'s existing `POST /ctacteprov` calls (which
      don't send `iva`/`percepcion`/`insumos`) still succeed unchanged
      against the updated endpoint. Covered by
      `test_create_factura_via_http_and_list_pagos` (sends none of the
      three, asserts 201) plus `test_iva_and_percepcion_persist_and_default_to_zero`'s
      no-values case.
- [x] 6.2 Confirm OpenAPI docs (`/docs`) reflect the new fields and routes.
      Verified against the running app (local Docker DB): `/docs` returns
      200; `/openapi.json` lists all three new routes
      (`GET/POST /costos/ctacteprov/{entry_id}/insumos`,
      `DELETE /costos/ctacteprov/{entry_id}/insumos/{detalle_id}`) and both
      `CuentaCorrienteProveedorCreate`/`*Read` schemas include
      `iva`/`percepcion`/`insumos`.
