## 1. Remitos reportes (read-only)

- [x] 1.1 Add `ProductoPendienteItem`, `ResponsableProductosPendientes`,
      `ProductosPendientesPorDia`, and `RemitosPendientesPorDia` schemas
      (new file `app/schemas/remitos_reportes.py`), mirroring mayorista's
      `PendientesPorDiaSchema` / `ProductoItemSchema` /
      `ResponsableProductosSchema` / `ProductosPendientesPorDiaSchema` shapes;
      reuse `app.schemas.remitos.RemitoRead` for individual remito items.
- [x] 1.2 Create `app/routers/remitos_reportes.py` with
      `router = APIRouter(prefix="/remitos-reportes", tags=["remitos-reportes"])`.
- [x] 1.3 Implement `GET /pendientes-entrega`: query all `Remitos` (no
      estado/fecha filter — matches mayorista's current actual behavior,
      not its stale docstring), ordered by `fecha_entrega` asc, mapped
      through `RemitoRead.from_orm_row`.
- [x] 1.4 Implement `GET /pendientes-por-dia` with optional
      `fecha_desde`/`fecha_hasta` query params filtering `fecha_entrega`;
      group the same unfiltered set by the date portion of `fecha_entrega`,
      computing per-estado counts (including `ENTREGADO`) from each
      remito's `estado` property.
- [x] 1.5 Implement `GET /productos-pendientes-por-dia` with optional
      `fecha_desde`/`fecha_hasta` params, using an async raw-SQL query
      (`session.execute(text(...))`) joining `costos_remitodetalles` /
      `costos_remitos` / `costos_productos`, filtering
      `fecha_facturacion IS NULL` only (no `fecha_recibido` filter —
      matches mayorista's current query), summing
      `cantidad - COALESCE(entregado, 0)` grouped by delivery date and
      `responsable`, sorted by date asc then responsable alphabetically.
- [x] 1.6 Register the router in `app/main.py`:
      `app.include_router(remitos_reportes.router, prefix="/costos")`.
- [x] 1.7 Tests (new `tests/unit/test_remitos_reportes.py`): all-remitos
      (unfiltered, including `ENTREGADO`) returned by both endpoint 1 and
      2, empty-result case, day/estado grouping and counts,
      fecha_desde/fecha_hasta filtering, partial-entrega quantity math
      (`cantidad=10, entregado=4` → pending 6) and `fecha_facturacion`
      filtering on endpoint 3, responsable grouping and
      alphabetical sort — covering every scenario in
      `specs/remitos-reportes/spec.md`.

## 2. Remito estado transitions and edit/delete guard

- [x] 2.1 Add a `VALID_TRANSITIONS` mapping (implemented in
      `app/services/remitos_service.py` alongside the other remito business
      logic, rather than `app/models/remitos.py`) keyed on this repo's
      existing estado strings (`PENDIENTE → EN_PREPARACION → PREPARADO →
      EN CAMINO → ENTREGADO`), mapping each source estado to its single
      valid next estado and the timestamp field to set
      (`fecha_preparacion`/`fecha_listo`/`fecha_despacho`/`fecha_recibido`).
- [x] 2.2 Add `EstadoTransitionRequest` schema (`nuevo_estado: str`) to
      `app/schemas/remitos.py`.
- [x] 2.3 Add `transition_estado(session, remito, nuevo_estado)` to
      `app/services/remitos_service.py`: look up the valid next estado from
      2.1, raise 422 (`HTTPException`) if `nuevo_estado` doesn't match,
      otherwise set the corresponding timestamp field to
      `datetime.now(timezone.utc)`, commit, and return the refreshed remito
      (reuse `get_remito` for the reload).
- [x] 2.4 Add `PATCH /{remito_id}/estado` to `app/routers/remitos.py`,
      `dependencies=[Depends(require_api_key)]`, calling
      `service.transition_estado`.
- [x] 2.5 Add a `_ensure_pendiente(remito)` helper in `app/routers/remitos.py`
      (or `remitos_service.py`) raising 422 if `remito.estado != "PENDIENTE"`;
      call it at the top of `update_remito` and `delete_remito` before any
      mutation.
- [x] 2.6 Tests (extend `tests/unit/test_remitos_clientes.py` or add
      `tests/unit/test_remitos_estado.py`): valid single-step transition,
      skipped-transition rejection, backward-transition rejection,
      transition without API key rejected with 401, PUT/DELETE succeed in
      `PENDIENTE`, PUT/DELETE rejected with 422 once estado has advanced —
      covering every scenario in `specs/remito-estado/spec.md`.

## 3. Productos listing filter

- [x] 3.1 Add `solo_habilitados: bool = True` query param to
      `list_productos` in `app/routers/productos.py`; when `True`, add
      `.where(Productos.habilitado.is_(True))` to the existing query,
      composing with the existing `nombre` filter and ordering.
- [x] 3.2 Tests (extend `tests/unit/test_productos*.py` or wherever
      productos listing is currently tested): default excludes disabled,
      `solo_habilitados=false` includes disabled, filter composes with
      `nombre` search — covering every scenario in
      `specs/productos-listado/spec.md`.

## 4. Wrap-up

- [x] 4.1 Update `README.md`'s endpoint list (if one exists documenting
      `/costos/*` routes) to include the new `remitos-reportes` endpoints,
      the `PATCH /remitos/{id}/estado` endpoint, and the `solo_habilitados`
      param.
- [x] 4.2 Run `pytest tests/unit -q` and confirm the full suite passes with
      the new tests included.
- [x] 4.3 Run `openspec validate merge-mayorista-remitos-api --type change
      --strict --json` and confirm it passes.
