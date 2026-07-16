## Why

`panacea-mayorista-backend` is a separate FastAPI service that reads/writes the
same Postgres tables this project already models (`clientes`, `costos_productos`,
`costos_remitos`, `costos_remitodetalles`). This repo already absorbed its
clientes/productos/remitos CRUD basics some time ago (in its own async +
service-layer + `X-API-Key` style), but mayorista has since evolved three things
this repo lacks: read-only pending-delivery reports, an enforced remito
state-machine, and a default-enabled-only productos filter. Consolidating them
here removes the need to keep two backends in sync against one database and
gives this API's consumers feature parity with mayorista under the `/costos`
prefix this project already uses everywhere.

## What Changes

- Add three read-only reporting endpoints under `/costos/remitos-reportes`,
  ported from mayorista's `/reports/*`, reusing the existing `Remitos` /
  `RemitoDetalles` / `Productos` models (no new tables). Note: despite the
  "pendientes" naming (kept for continuity with mayorista), the first two
  endpoints apply no pending-only filter — this matches mayorista's actual
  current behavior after two deliberate filter-removal commits there
  (`13b8d18`, `74ed0c0`), not the stale docstrings still in its source:
  - all remitos, ordered by `fecha_entrega` ascending
  - the same unfiltered set grouped by delivery day, with per-estado counts
  - pending product quantities (excluding already-invoiced remitos only)
    grouped by delivery day and by `Productos.responsable`, with optional
    `fecha_desde`/`fecha_hasta` filters
- Add `PATCH /costos/remitos/{id}/estado`, validating transitions against the
  existing linear state machine already implied by `Remitos.estado`
  (`creado → en_produccion → preparando → listo_entregar → en_entrega →
  facturado`), rejecting skipped or backward transitions with 422. Protected
  by the same `require_api_key` dependency already used on other write
  endpoints in this repo.
- **BREAKING**: `PUT /costos/remitos/{id}` and `DELETE /costos/remitos/{id}`
  will start rejecting the request (422) unless the remito is still in
  `creado` state. Today both endpoints allow editing or deleting a remito in
  any state, including a `facturado` one. Existing API consumers who currently
  mutate remitos past the `creado` state will need to move to the new
  `PATCH .../estado` endpoint for state changes and stop editing/deleting
  once a remito has moved past `creado`.
- Add a `solo_habilitados` query parameter (default `true`) to
  `GET /costos/productos`, matching mayorista's default of hiding disabled
  productos from listings. **BREAKING**: the default listing response changes
  — disabled productos, previously included, are now excluded unless the
  caller passes `solo_habilitados=false`.

## Capabilities

### New Capabilities
- `remitos-reportes`: read-only reporting endpoints over remitos/productos
  pendientes, grouped by delivery day and by responsable.
- `remito-estado`: the remito state-machine — valid transition sequence, the
  `PATCH .../estado` endpoint, and the state guard applied to editing/deleting
  a remito.

### Modified Capabilities
(none — `productos` and `remitos` listing/CRUD behavior were never captured
as OpenSpec capabilities before this change; the productos listing filter is
folded into `remito-estado`'s sibling capability below instead of retrofitting
a full unrelated CRUD spec.)
- `productos-listado`: (new, listed here for visibility) adds the
  `solo_habilitados` default filter to `GET /costos/productos`.

## Impact

- **Code**: new `app/routers/remitos_reportes.py` (or similar), new schemas
  for report shapes, additions to `app/routers/remitos.py` /
  `app/services/remitos_service.py` for the estado guard and transition
  endpoint, a small addition to `app/routers/productos.py` for the filter.
  Registration in `app/main.py` following the existing
  `app.include_router(..., prefix="/costos")` pattern.
- **API consumers**: any client currently doing unrestricted `PUT`/`DELETE`
  on non-`creado` remitos breaks (see BREAKING note above). Any client
  relying on `GET /costos/productos` returning disabled productos by default
  breaks unless it passes `solo_habilitados=false`.
- **Database**: no schema changes — all three efforts read/write existing
  tables and columns already modeled in `app/models/remitos.py` and
  `app/models/productos.py`.
- **Out of scope** (reconciled during exploration, not carried over):
  clientes/productos/remitos CRUD basics (already ported and more mature
  here), mayorista's lack of auth (this repo's `X-API-Key` convention wins
  for new endpoints), the `fecha_carga` vs `fecha_entrega` default-ordering
  difference on `GET /costos/remitos`, and the differing estado filter
  query-param spelling/casing between the two repos.
