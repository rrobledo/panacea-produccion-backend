-- One-time backfill: costos_remitos/costos_remitodetalles -> the new
-- Pedidos/Remitos model (see
-- openspec/changes/pedidos-y-remitos/design.md, Decision 7 and Migration
-- Plan step 4).
--
-- Pure-SQL, no Python port (unlike scripts/migrate_ctacteprov_to_compras.py
-- /.sql — this one wasn't asked for a Python version). Same overall shape
-- as scripts/migrate_ctacteprov_to_compras.sql:
--   - TRUNCATE ... RESTART IDENTITY CASCADE on every target table first, so
--     the script is safely re-runnable from a clean slate.
--   - id-map temp tables populated via nextval(pg_get_serial_sequence(...))
--     reserved up front, so later INSERTs can join back to the legacy id.
--   - A closing block of verification SELECTs instead of a printed summary.
--
-- What this script does:
--   - Every costos_remitos row becomes exactly one Pedido (+ one
--     PedidoDetalle per costos_remitodetalles row: cantidad_pedida =
--     cantidad, cantidad_entregada = COALESCE(entregado, 0)).
--   - Pedido.estado is derived from the legacy computed estado (the same
--     fecha_preparacion/fecha_listo/fecha_despacho/fecha_recibido/
--     fecha_facturacion precedence Remitos.estado used to compute in
--     Python): creado -> PENDIENTE, en_produccion -> EN_PREPARACION,
--     preparando -> PREPARADO, listo_entregar -> LISTO_PARA_ENTREGA,
--     en_entrega -> ENTREGADO, facturado -> ENTREGADO (there's no pedido
--     equivalent for "facturado"; it collapses into ENTREGADO with a note
--     in observaciones).
--   - A Remito (tipo=VENTA, pedido_id + cliente_id pointing back at the
--     Pedido just created) is generated ONLY for legacy rows whose
--     computed estado is listo_entregar/en_entrega/facturado (i.e.
--     fecha_despacho IS NOT NULL) AND that have at least one detalle line
--     with entregado > 0 — the same threshold that triggers automatic
--     remito generation in the live system (a Pedido reaching
--     LISTO_PARA_ENTREGA/ENTREGADO), and the same "don't generate an empty
--     remito" rule from specs/pedidos/spec.md. Rows that crossed the
--     threshold with nothing delivered are listed in the verification
--     block at the end instead of silently getting a remito with no
--     lines.
--   - The generated Remito's own timestamps start straight at EN_TRANSITO
--     (fecha_despacho = legacy fecha_despacho) and, if the legacy row
--     reached en_entrega/facturado, RECIBIDO (fecha_recibido = legacy
--     fecha_recibido). fecha_listo on the new Remito is left NULL — that
--     step is represented on the Pedido side (EN_PREPARACION/PREPARADO)
--     instead; there's no independent legacy timestamp for the remito's
--     own LISTO phase. remitos_remito no longer has a fecha_preparacion
--     column at all (see migrations/0020_remito_sin_en_preparacion.sql —
--     the live Remito model dropped that step). Accepted limitation of
--     reconstructing two separate state machines out of one legacy one —
--     see design.md Risks.
--   - Nothing is migrated into sucursales_sucursal or generates a
--     TRANSFERENCIA remito: the legacy model has no concept of internal
--     stock transfers, so there's nothing to map. Transferencia remitos
--     only ever get created going forward, through the new API.
--
-- What this script does NOT do:
--   - It does not modify or drop costos_remitos/costos_remitodetalles —
--     they remain exactly as-is, a read-only historical source. Dropping
--     them is a separate, manual, later step (see design.md Migration
--     Plan step 7), deliberately out of scope here.
--   - It does not attempt to reconstruct multiple remitos per pedido
--     (partial-delivery tranches) — the legacy model only ever recorded
--     one dispatch per row, so every migrated Pedido gets at most one
--     Remito.
--
-- Usage (same BEGIN/ROLLBACK convention as
-- scripts/migrate_ctacteprov_to_compras.sql):
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "BEGIN;" -f scripts/migrate_remitos_to_pedidos_remitos.sql -c "ROLLBACK;"   -- dry run
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 -f scripts/migrate_remitos_to_pedidos_remitos.sql                          -- apply for real
--
-- NOTE: table/column names below follow the schema described in
-- openspec/changes/pedidos-y-remitos/tasks.md group 1. That migration
-- hasn't been written yet at the time this script was authored — double
-- check the actual DDL (migrations/00NN_pedidos_remitos_sucursales.sql)
-- once it exists, and adjust column names here if anything changed during
-- implementation.

-- Wipe every target table before migrating, so this script can be re-run
-- from a clean slate instead of aborting or duplicating data on a second
-- run. RESTART IDENTITY resets pedidos_pedido/remitos_remito's sequences
-- too, so the nextval() reservations below start from 1 every time.
-- costos_remitos/costos_remitodetalles are NOT in this list — see header.
TRUNCATE TABLE
    remitos_remito_detalle,
    remitos_remito,
    pedidos_pedido_detalle,
    pedidos_pedido
RESTART IDENTITY CASCADE;

-- Normalized snapshot of every legacy remito with its computed estado,
-- mirroring Remitos.estado's precedence exactly (app/models/remitos.py):
-- facturado > en_entrega > listo_entregar > preparando > en_produccion >
-- creado, based on which timestamp is set furthest down that list.
CREATE TEMP TABLE _legacy AS
SELECT
    r.*,
    CASE
        WHEN r.fecha_facturacion IS NOT NULL THEN 'facturado'
        WHEN r.fecha_recibido IS NOT NULL THEN 'en_entrega'
        WHEN r.fecha_despacho IS NOT NULL THEN 'listo_entregar'
        WHEN r.fecha_listo IS NOT NULL THEN 'preparando'
        WHEN r.fecha_preparacion IS NOT NULL THEN 'en_produccion'
        ELSE 'creado'
    END AS estado_legacy
FROM costos_remitos r;

-- id-map tables: legacy costos_remitos.id -> new pedidos_pedido.id /
-- remitos_remito.id. ids are reserved up front (via nextval on the real
-- sequence, in legacy-id order) so later INSERTs can join back to the
-- source row's legacy id, same reason as
-- scripts/migrate_ctacteprov_to_compras.sql.
CREATE TEMP TABLE _pedido_id_map (legacy_id BIGINT PRIMARY KEY, pedido_id BIGINT NOT NULL);
CREATE TEMP TABLE _remito_id_map (legacy_id BIGINT PRIMARY KEY, remito_id BIGINT NOT NULL);

INSERT INTO _pedido_id_map (legacy_id, pedido_id)
SELECT id, nextval(pg_get_serial_sequence('pedidos_pedido', 'id'))
FROM _legacy
ORDER BY id;

-- Only legacy rows that reached listo_entregar/en_entrega/facturado AND
-- have at least one delivered line get a Remito reserved — see header for
-- why an empty remito is deliberately not generated.
INSERT INTO _remito_id_map (legacy_id, remito_id)
SELECT l.id, nextval(pg_get_serial_sequence('remitos_remito', 'id'))
FROM _legacy l
WHERE l.estado_legacy IN ('listo_entregar', 'en_entrega', 'facturado')
  AND EXISTS (
      SELECT 1 FROM costos_remitodetalles d
      WHERE d.remito_id = l.id AND COALESCE(d.entregado, 0) > 0
  )
ORDER BY l.id;

-- ==========================================================================
-- costos_remitos -> Pedido
-- ==========================================================================

INSERT INTO pedidos_pedido (
    id, cliente_id, vendedor, estado, fecha_carga, fecha_entrega, observaciones
)
SELECT
    m.pedido_id,
    l.cliente_id,
    l.vendedor,
    CASE l.estado_legacy
        WHEN 'creado' THEN 'PENDIENTE'
        WHEN 'en_produccion' THEN 'EN_PREPARACION'
        WHEN 'preparando' THEN 'PREPARADO'
        WHEN 'listo_entregar' THEN 'LISTO_PARA_ENTREGA'
        WHEN 'en_entrega' THEN 'ENTREGADO'
        WHEN 'facturado' THEN 'ENTREGADO'
    END,
    l.fecha_carga,
    l.fecha_entrega,
    '[migrado de costos_remitos#' || l.id || ', estado_legacy=' || l.estado_legacy || ']'
        || CASE WHEN l.observaciones IS NOT NULL AND l.observaciones <> ''
                THEN ' | ' || l.observaciones ELSE '' END
FROM _legacy l
JOIN _pedido_id_map m ON m.legacy_id = l.id;

-- costos_remitodetalles -> PedidoDetalle, one line per legacy detalle row.
-- cantidad_remitida is set equal to cantidad_entregada when a Remito was
-- generated for this header (see below — that Remito's lines are exactly
-- the ones with entregado > 0, so this line has already been "remitido"),
-- 0 otherwise (matches a live Pedido that never reached
-- LISTO_PARA_ENTREGA/ENTREGADO).
INSERT INTO pedidos_pedido_detalle (
    pedido_id, producto_id, cantidad_pedida, cantidad_entregada, cantidad_remitida, observaciones
)
SELECT
    m.pedido_id,
    d.producto_id,
    d.cantidad,
    COALESCE(d.entregado, 0),
    CASE WHEN rm.remito_id IS NOT NULL THEN COALESCE(d.entregado, 0) ELSE 0 END,
    d.observaciones
FROM costos_remitodetalles d
JOIN _pedido_id_map m ON m.legacy_id = d.remito_id
LEFT JOIN _remito_id_map rm ON rm.legacy_id = d.remito_id;

-- ==========================================================================
-- costos_remitos (listo_entregar/en_entrega/facturado, con algo entregado)
-- -> Remito
-- ==========================================================================

INSERT INTO remitos_remito (
    id, tipo, cliente_id, pedido_id,
    origen_sucursal_id, destino_sucursal_id,
    vendedor, observaciones, fecha_carga,
    fecha_listo, fecha_despacho, fecha_recibido
)
SELECT
    rm.remito_id,
    'VENTA',
    l.cliente_id,
    pm.pedido_id,
    NULL,
    NULL,
    l.vendedor,
    '[migrado de costos_remitos#' || l.id || ', estado_legacy=' || l.estado_legacy || ']',
    l.fecha_despacho, -- the remito only starts existing once the legacy row was dispatched
    NULL,             -- no legacy timestamp for the remito's own LISTO phase (see header)
    l.fecha_despacho,
    CASE WHEN l.estado_legacy IN ('en_entrega', 'facturado') THEN l.fecha_recibido ELSE NULL END
FROM _legacy l
JOIN _remito_id_map rm ON rm.legacy_id = l.id
JOIN _pedido_id_map pm ON pm.legacy_id = l.id;

-- RemitoDetalle: one line per legacy detalle row actually delivered.
INSERT INTO remitos_remito_detalle (remito_id, producto_id, cantidad, observaciones)
SELECT
    rm.remito_id,
    d.producto_id,
    d.entregado,
    d.observaciones
FROM costos_remitodetalles d
JOIN _remito_id_map rm ON rm.legacy_id = d.remito_id
WHERE COALESCE(d.entregado, 0) > 0;

-- ==========================================================================
-- Verification / summary
-- ==========================================================================

-- Overall counts.
SELECT
    'resumen' AS reporte,
    (SELECT count(*) FROM _legacy) AS remitos_legacy_totales,
    (SELECT count(*) FROM _pedido_id_map) AS pedidos_migrados,
    (SELECT count(*) FROM _remito_id_map) AS remitos_generados,
    (SELECT count(*) FROM pedidos_pedido_detalle) AS pedido_detalle_migrados,
    (SELECT count(*) FROM remitos_remito_detalle) AS remito_detalle_migrados;

-- Pedidos por estado migrado, para chequeo rápido de la distribución.
SELECT 'pedidos_por_estado' AS reporte, estado, count(*) AS total
FROM pedidos_pedido
GROUP BY estado
ORDER BY estado;

-- Filas legacy que alcanzaron listo_entregar/en_entrega/facturado pero no
-- generaron Remito porque ninguna línea tenía entregado > 0 — candidatas a
-- revisión manual (dato legacy inconsistente: se despachó "nada").
SELECT
    'listo_entregar_sin_remito_generado' AS reporte,
    l.id AS legacy_id,
    l.estado_legacy,
    l.fecha_despacho
FROM _legacy l
WHERE l.estado_legacy IN ('listo_entregar', 'en_entrega', 'facturado')
  AND NOT EXISTS (SELECT 1 FROM _remito_id_map rm WHERE rm.legacy_id = l.id)
ORDER BY l.id;

-- costos_remitodetalles huérfanas: remito_id que no matchea ningún
-- costos_remitos (el modelo legacy permite remito_id NULL/inválido, ver
-- app/models/remitos.py) — no generan PedidoDetalle, listadas para
-- inspección manual.
SELECT 'detalle_legacy_huerfano' AS reporte, d.id AS detalle_id, d.remito_id
FROM costos_remitodetalles d
WHERE d.remito_id IS NULL
   OR NOT EXISTS (SELECT 1 FROM costos_remitos r WHERE r.id = d.remito_id)
ORDER BY d.id;
