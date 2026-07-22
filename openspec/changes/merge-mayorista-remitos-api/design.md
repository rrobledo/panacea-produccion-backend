## Context

`panacea-produccion-backend` (this repo) and `panacea-mayorista-backend`
(sibling repo, `../panacea-mayorista-backend`) both read/write the same
Postgres database. This repo already has async, service-layer, `X-API-Key`-
gated routers for `clientes`/`productos`/`remitos` mounted under `/costos`
(`app/main.py`), covering the same tables mayorista uses
(`clientes`, `costos_productos`, `costos_remitos`, `costos_remitodetalles`,
modeled in `app/models/clientes.py`, `app/models/productos.py`,
`app/models/remitos.py`). Mayorista is a smaller, older, sync (`Session`,
not `AsyncSession`), un-authenticated FastAPI app (`app/routers/*.py` there:
`clientes.py`, `productos.py`, `remitos.py`, `reports.py`) that has picked up
three things since the original port that this repo lacks: pending-delivery
reports, a remito state-machine guard, and a default-enabled-only productos
filter. `Remitos.estado` (`app/models/remitos.py:30`) already computes the
same five-state sequence mayorista enforces via
`app/state.py` (`VALID_TRANSITIONS`) there — this repo just never enforced
transitions or gated edit/delete on it.

## Goals / Non-Goals

**Goals:**
- Port mayorista's three `/reports/*` endpoints as `/costos/remitos-reportes/*`,
  reusing existing models/schemas, adding no new tables.
- Enforce mayorista's remito state machine here: a `PATCH .../estado`
  endpoint, and a guard rejecting `PUT`/`DELETE` on non-`creado` remitos.
- Add `solo_habilitados` (default `true`) to `GET /costos/productos`.
- Keep every new/changed endpoint under `/costos`, consistent with this
  project's existing router registration pattern.

**Non-Goals:**
- Re-porting clientes/productos/remitos CRUD basics — already done, and this
  repo's version (async, service layer, `X-API-Key` auth) is treated as the
  canonical implementation going forward, not mayorista's.
- Adopting mayorista's lack of auth — new endpoints follow this repo's
  `require_api_key`-on-writes convention; reports are read-only so get no
  auth, consistent with e.g. `app/routers/produccion_stats.py` already being
  open on reads.
- Reconciling the `GET /costos/remitos` default-ordering difference
  (mayorista: `fecha_carga` desc; here: `fecha_entrega` asc) — left as-is,
  noted as an open question below.
- Reconciling the differing estado-filter query-param spelling/casing
  between the two repos — no known consumer depends on mayorista's exact
  values, not addressed here.
- Any change to `panacea-mayorista-backend` itself — this change is
  one-directional (mayorista → here); mayorista's own fate (decommission,
  keep as-is, etc.) is a separate decision not made by this change.

## Decisions

### 1. Reports live in a new router/capability, not folded into `remitos.py`
`app/routers/remitos_reportes.py`, mounted at `/costos` (giving
`/costos/remitos-reportes/pendientes-entrega` etc.), mirroring mayorista's
`reports.py` structure and its own `/reports` prefix, renamed to
`remitos-reportes` for clarity now that it sits alongside this repo's other
`/costos` routers rather than as a single-service root-level concern.
Reuses `app.schemas.remitos.RemitoRead` for the two remito-shaped reports;
only `productos-pendientes-por-dia` needs new response schemas
(`ProductoPendienteItem`, `ResponsableProductos`,
`ProductosPendientesPorDia`), matching mayorista's `schemas.py` shapes.

**Alternative considered**: add report functions as new endpoints inside
`remitos.py`. Rejected — reports are a distinct read-model/reporting
concern (grouping, aggregation) versus `remitos.py`'s CRUD concern; keeping
them separate matches how mayorista itself separated `remitos.py` from
`reports.py`, and matches this repo's existing pattern of dedicated stats
routers (`produccion_stats.py`) rather than bolting stats onto CRUD routers.

### 2. `productos-pendientes-por-dia` keeps mayorista's raw SQL, adjusted for this repo's schema/engine
Mayorista's query joins `costos_remitodetalles` / `costos_remitos` /
`costos_productos` directly via `sqlalchemy.text(...)` against a sync
`Session`. This repo's engine is async (`AsyncSession`, `app/db.py`); the
query is re-expressed as an async `session.execute(text(...))` call — the
SQL body and grouping logic are unchanged, only the execution mechanics
differ. Filters `fecha_facturacion IS NULL` (not yet invoiced) — same
condition mayorista uses instead of `fecha_recibido`, since mayorista's own
history shows both filters were tried and reverted before landing on
`fecha_facturacion IS NULL` alone (see mayorista commits `74ed0c0`,
`13b8d18`) — porting the final state, not the intermediate ones.

**Alternative considered**: express the same aggregation via the ORM
(`Remitos`/`RemitoDetalles`/`Productos` joins + Python-side grouping) instead
of raw SQL, for consistency with the rest of this repo's ORM-first style.
Rejected for this change — the raw SQL is already correct and tested in
mayorista; rewriting it in the ORM risks subtly changing the aggregation
(e.g. `SUM(cantidad - COALESCE(entregado, 0))`) for no behavioral gain. Can
be revisited later if this repo's convention against raw SQL is a hard rule
(not confirmed either way during exploration).

### 3. Estado transition validation reuses `Remitos.estado`'s existing precedence, doesn't duplicate mayorista's `derive_estado`/`EstadoRemito` enum
This repo already computes `estado` as a property on the `Remitos` model
(`app/models/remitos.py:30`) and mirrors it as SQL conditions in
`app/routers/remitos.py`'s `_ESTADO_CONDITIONS` for filtering. The new
transition endpoint adds a `VALID_TRANSITIONS`-equivalent mapping keyed on
this repo's existing estado string values (`"PENDIENTE"`, `"EN_PREPARACION"`,
`"PREPARADO"`, `"EN CAMINO"`, `"ENTREGADO"`) rather than introducing
mayorista's differently-spelled `EstadoRemito` enum
(`creado`/`en_produccion`/.../`facturado`). One state vocabulary per repo;
the request body for `PATCH .../estado` takes the target state's driving
field transition (e.g. `{"nuevo_estado": "EN_PREPARACION"}`), validated
against the same linear sequence mayorista enforces, just spelled this
repo's way.

**Alternative considered**: import mayorista's exact `EstadoRemito` enum
values into the request contract, so a mayorista frontend integrating
against this API needs no translation layer. Rejected — mixing two state
vocabularies in one repo (property values in one casing, transition-request
values in another) is a worse long-term cost than requiring
whatever mayorista-side caller adopts this endpoint to send this repo's
existing values, which it already must do today for the `estado` filter
on `GET /costos/remitos`.

### 4. PUT/DELETE guard implemented as a shared helper, reused by both endpoints
`app/routers/remitos.py`'s `update_remito` and `delete_remito` both gain a
check via a shared `_ensure_creado(remito)` helper (raises 422 if
`remito.estado != "PENDIENTE"`, this repo's spelling for mayorista's
`creado`), called before mutating/deleting. Keeps the two call sites from
drifting on the error message/status code.

## Risks / Trade-offs

- **[Breaking change to PUT/DELETE]** Any existing caller currently editing
  or deleting remitos past `creado`/`PENDIENTE` will start getting 422s.
  → Mitigation: called out explicitly as **BREAKING** in the proposal;
  this is a deliberate behavior port from mayorista, not an accidental
  regression. No code search was run against consumer apps (out of repo
  scope) — worth the user confirming no current integration relies on
  post-`creado` edits before this ships.
- **[Breaking change to productos listing default]** `solo_habilitados=true`
  default hides previously-visible disabled productos from
  `GET /costos/productos` unless the caller opts out.
  → Mitigation: same as above — explicit opt-out query param preserves the
  old behavior for any caller that adds `?solo_habilitados=false`.
- **[Raw SQL portability]** The ported `productos-pendientes-por-dia` query
  uses Postgres-specific `DATE(...)` and named-parameter binding; fine since
  both repos already target Postgres exclusively, but worth flagging since
  it's the one piece of raw SQL in an otherwise ORM-first router set.
  → Mitigation: none needed unless this repo later targets multiple DB
  backends (not currently planned).
- **[State vocabulary translation]** Any mayorista-side consumer adopting
  the new `PATCH .../estado` endpoint must translate mayorista's
  `EstadoRemito` values to this repo's spelling (decision 3).
  → Mitigation: documented in the capability spec; a translation table is
  small (5 values) and one-directional.

## Migration Plan

No data migration — no schema changes. Rollout is a normal code deploy:
1. Ship the three new report endpoints and the `solo_habilitados` param
   first — both are additive/opt-in, zero risk to existing callers.
2. Ship the `PATCH .../estado` endpoint alongside the PUT/DELETE guard in
   the same deploy, since the guard is only safe to enable once callers have
   an alternative (the new PATCH endpoint) to change state.
3. No rollback complexity beyond a normal revert — nothing is destructive or
   irreversible at the data layer.

## Open Questions

- Should `GET /costos/remitos`'s default ordering be reconciled with
  mayorista's `fecha_carga` desc, or is this repo's `fecha_entrega` asc
  intentional and should stay? (left unresolved per proposal scope)
- Is any current API consumer relying on editing/deleting remitos past
  `creado`? Needs a answer before shipping the BREAKING PUT/DELETE guard.
- Should the `PATCH .../estado` endpoint accept mayorista's state spelling
  as an additional alias, to ease integration for a mayorista-side caller,
  or is a single vocabulary preferred? (design assumes single vocabulary —
  decision 3 — but this wasn't confirmed with the user)
