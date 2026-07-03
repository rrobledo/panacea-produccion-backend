## Context

`costos_cuentacorrienteproveedor` is a Django-managed table in the shared
Postgres instance also used by `panacea-backend` (see reference model at
`panacea-backend/costos/models.py:145-161`). The in-flight
`produccion-costos-api` change in this repo plans to port that table's CRUD
(`GET/POST /ctacteprov`, `GET/PUT/PATCH/DELETE /ctacteprov/{id}`) into this
FastAPI service **read/write only, no DDL** — schema ownership stays with
Django's migration history in `panacea-backend`.

This change needs new DDL: two columns on that table (`iva`, `percepcion`)
and a brand-new child table (`costos_cuentacorrienteproveedordetalle`) for
per-insumo invoice detail. The user has explicitly decided (see proposal)
that this DDL is authored and applied from `panacea-produccion-backend`
directly via raw SQL, not as a Django migration in `panacea-backend`. This
is a deliberate, scoped deviation from the otherwise-consistent "Django owns
the schema" pattern used everywhere else in this project, made because this
service is the one driving the new fields and has no existing Alembic/SQL
migration tooling to build on top of yet.

## Goals / Non-Goals

**Goals:**
- Add `iva`/`percepcion` to `costos_cuentacorrienteproveedor` without
  breaking any existing row (defaults, no `NOT NULL` on backfill).
- Add `costos_cuentacorrienteproveedordetalle` as a proper 1-to-many child of
  `costos_cuentacorrienteproveedor`, referencing `costos_insumos`.
- Nested read/write API consistent with the existing `RemitoDetalles` /
  `productos` nested-create pattern already used elsewhere in this domain,
  so the shape is familiar to `panacea-front` if it adopts it later.
- A migration mechanism this service can re-run safely (idempotent) given
  there's no disposable dev database — same constraint the parent change
  already operates under.

**Non-Goals:**
- Backfilling `iva`/`percepcion` for historical rows — they default to `0`,
  no computed backfill from `importe_total`.
- Migrating `panacea-backend`'s Django model/migrations to know about these
  new columns/table. Django's `CuentaCorrienteProveedor` model simply won't
  have `iva`/`percepcion` mapped, and won't know about the detalle table,
  until/unless a future, separate change updates it there. This is an
  accepted, temporary schema/ORM-model divergence between the two services.
- A generic "migration framework" (Alembic) for this service — a single
  hand-written, idempotent SQL script is enough for this one change; a full
  Alembic setup is a separate decision if more schema changes accumulate.
- Editing/updating an existing detail row (`PUT`/`PATCH`) — only create
  (`POST`), list (`GET`), and delete (`DELETE`) are in scope, matching what
  the proposal calls "populate it."

## Decisions

**D1 — DDL lives in `panacea-produccion-backend/migrations/` as a single
hand-written SQL file, applied manually (`psql -f`) against the shared
Postgres instance, not via an ORM migration tool.**
No ORM/migration tooling exists yet in this repo (SQLAlchemy models
themselves aren't written yet — the parent change is still unimplemented).
Introducing Alembic for one migration is more setup than the change
warrants; a plain, idempotent (`IF NOT EXISTS`) SQL script is sufficient and
auditable.
*Alternative considered*: Django migration in `panacea-backend` (rejected
per explicit user decision — see proposal); Alembic in this repo (rejected
for now — no other migrations exist yet to justify the tooling, revisit if
a second schema change lands).

**D2 — New table name `costos_cuentacorrienteproveedordetalle`, no
underscore before `detalle`.**
Matches Django's default table-naming convention already used for every
other table in this schema (`<app_label>_<modelnamelowercased>`, e.g.
`costos_cuentacorrienteproveedorafect`, `costos_remitodetalles`). Keeping
the same convention avoids an oddly-named outlier table even though this
one isn't Django-managed.

**D3 — Detail rows store `subtotal` as an input value, not a computed
column.**
The API accepts `subtotal` directly from the caller on `POST`, same as
`cantidad`. This matches the proposal's literal ask ("count and subtotal")
and avoids inventing a price field that wasn't requested; the existing
`Costos` (producto→insumo) table follows the same pattern of not persisting
a derived amount.
*Alternative considered*: also require/store `precio_unitario` and compute
`subtotal = cantidad * precio_unitario` server-side — rejected as scope
creep beyond what was asked; the caller already knows the subtotal from the
invoice line they're transcribing.

**D4 — `ON DELETE CASCADE` from `costos_cuentacorrienteproveedordetalle.cuentacorrienteproveedor_id`
to the parent, `ON DELETE RESTRICT` from `insumo_id` to `costos_insumos`.**
Deleting an invoice should clean up its own detail rows (they have no
independent meaning without the parent). Deleting an `insumo` that's
referenced by existing detail rows should be blocked, matching the
`RESTRICT` convention used for every other FK to `costos_insumos`/
`costos_productos` in the reference schema (e.g. `Costos.insumo`,
`Costos.producto`).

**D5 — Nested `insumos` array on `POST /ctacteprov`, plus a standalone
`POST /ctacteprov/{id}/insumos` for after-the-fact additions.**
Mirrors the existing `RemitosSerializer`/`RemitoDetalles` nested-create
pattern (create parent + children in one call) while also covering the
"populate it" case where detail rows are added to an invoice entered
earlier (e.g. corrections, or invoice detail arriving after the header).
*Alternative considered*: nested array only, no standalone endpoint —
rejected because the proposal explicitly asks for an API "to populate it,"
implying insertion isn't limited to creation time.

## Risks / Trade-offs

- **[Risk] Schema drift between Django's model layer and the actual
  Postgres schema** (Django's `CuentaCorrienteProveedor` model won't declare
  `iva`/`percepcion`/the new FK, but the columns/table will exist in the
  live DB) → *Mitigation*: documented explicitly here and in the proposal as
  an accepted, scoped exception; if `panacea-backend` later needs these
  fields, that's a follow-up Django migration using `migrations.AddField`
  with no `default` collision (columns already exist) — safe because Django
  migrations are declarative against a target state, not diffed against
  live DB contents at write time. Running `python manage.py makemigrations`
  in `panacea-backend` before that follow-up migration exists will not
  auto-detect these columns (they're not in `models.py`), so it will not
  generate a conflicting migration on its own.
- **[Risk] Running raw DDL directly against shared production Postgres,
  same constraint the parent change already lives with** → *Mitigation*:
  migration script uses `ADD COLUMN IF NOT EXISTS` / `CREATE TABLE IF NOT
  EXISTS` so it's safe to re-run; tested against a throwaway transaction
  (`BEGIN; ...; ROLLBACK;`) first per the Migration Plan below before the
  real `COMMIT`.
- **[Trade-off] No `PUT`/`PATCH` on individual detail rows** — a
  mis-entered `cantidad`/`subtotal` must be fixed via delete + re-create
  rather than in-place edit. Accepted for v1 scope; add an update endpoint
  later if this proves to be a common correction path.

## Migration Plan

1. Write `migrations/0001_ctacteprov_detalle_and_iva.sql`:
   - `ALTER TABLE costos_cuentacorrienteproveedor ADD COLUMN IF NOT EXISTS
     iva DOUBLE PRECISION DEFAULT 0, ADD COLUMN IF NOT EXISTS percepcion
     DOUBLE PRECISION DEFAULT 0;`
   - `CREATE TABLE IF NOT EXISTS costos_cuentacorrienteproveedordetalle (id
     BIGSERIAL PRIMARY KEY, cuentacorrienteproveedor_id BIGINT NOT NULL
     REFERENCES costos_cuentacorrienteproveedor(id) ON DELETE CASCADE,
     insumo_id INTEGER NOT NULL REFERENCES costos_insumos(id) ON DELETE
     RESTRICT, cantidad DOUBLE PRECISION NOT NULL, subtotal DOUBLE PRECISION
     NOT NULL);`
   - Index on `cuentacorrienteproveedor_id` (the `GET .../insumos` list
     query's access pattern).
2. Dry-run inside `BEGIN; ...; ROLLBACK;` against the shared instance to
   confirm no syntax/constraint errors before committing.
3. Apply for real (`BEGIN; ...; COMMIT;` or a single non-transactional run
   with `IF NOT EXISTS` guards, since it's idempotent either way).
4. Implement the SQLAlchemy models (`CuentaCorrienteProveedor` gains
   `iva`/`percepcion`; new `CuentaCorrienteProveedorDetalle` model),
   Pydantic schemas, router endpoints, and service functions in this repo.
5. Verify against the live schema (`\d costos_cuentacorrienteproveedor`,
   `\d costos_cuentacorrienteproveedordetalle`) that columns/FKs/cascade
   behavior match what was applied.
6. Rollback strategy: dropping the new column/table is a separate, manually
   reviewed SQL script (`ALTER TABLE ... DROP COLUMN`, `DROP TABLE`) — not
   auto-generated, since a rollback after real data has been written would
   be destructive; only run if this change is fully reverted before any
   production data uses the new fields.

## Open Questions

- Whether `panacea-backend`'s Django model layer should eventually be
  updated to declare `iva`/`percepcion`/the detalle table (so the Django
  admin/other Django-side code can see them) — deferred; not needed for
  this service's API to function, and out of scope for this change per the
  user's decision to keep the DDL here.
