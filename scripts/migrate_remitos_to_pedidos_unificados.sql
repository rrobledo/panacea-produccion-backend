-- Migración de datos: remitos_remito/remitos_remito_detalle -> el modelo
-- unificado de envíos (pedidos_pedido + pedidos_pedido_detalle). Ver
-- openspec/changes/unificar-pedidos-y-remitos/design.md, Decision 8.
--
-- Requiere migrations/0033_unificar_pedidos_remitos.sql ya aplicada.
--
-- Cada remito se clasifica en uno de dos grupos:
--   - GENERADO desde un pedido (se absorbe): pedido_id IS NOT NULL y además
--       * fecha_listo IS NULL — los que creó el backfill
--         scripts/migrate_remitos_to_pedidos_remitos.sql, o
--       * fecha_despacho = fecha_carga AND fecha_recibido = fecha_carga — los
--         que creó pedido_service._generar_remito en vivo (nacían RECIBIDO
--         con las cuatro fechas iguales).
--     Sus cantidades ya están en pedidos_pedido_detalle.cantidad_entregada,
--     así que no se crea nada: solo se registra el vínculo en
--     pedidos_remito_legacy y se verifica la suma contra cantidad_remitida.
--   - MANUAL (se convierte): todo lo demás (creado por POST /remitos, con o
--     sin pedido_id). Pasa a ser un pedido nuevo con es_remito = true:
--       * VENTA -> tipo CLIENTE; TRANSFERENCIA -> tipo SUCURSAL con
--         sucursal_id = destino y origen_sucursal_id = origen.
--       * LISTO/EN_TRANSITO -> LISTO_PARA_ENTREGA; RECIBIDO -> ENTREGADO. La
--         fecha de despacho de un remito EN_TRANSITO queda anotada en
--         observaciones (el estado no tiene equivalente).
--       * Líneas agrupadas por producto_id (el merge por producto de
--         update_pedido no admite duplicados): cantidad_pedida = 0,
--         cantidad_entregada = SUM(cantidad), fecha_creacion = la mínima.
--
-- Además:
--   - Completa origen_sucursal_id de los pedidos tipo SUCURSAL existentes
--     (el origen de su remito TRANSFERENCIA generado, o la única sucursal
--     FABRICA).
--   - Completa fecha_facturado/factura_referencia de los pedidos que vienen
--     de costos_remitos (observaciones '[migrado de costos_remitos#N, ...')
--     con costos_remitos.fecha_facturacion.
--
-- Lo que NO hace: no modifica ni borra remitos_remito*, ni
-- cantidad_remitida — eso es migrations/0034_drop_remitos.sql, en un
-- despliegue posterior a validar la verificación del final.
--
-- Re-ejecutable: los remitos ya vinculados en pedidos_remito_legacy se
-- saltean y los UPDATE solo completan valores NULL.
--
-- Uso:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "BEGIN;" -f scripts/migrate_remitos_to_pedidos_unificados.sql -c "ROLLBACK;"   -- dry run
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 -f scripts/migrate_remitos_to_pedidos_unificados.sql                          -- apply for real

DROP TABLE IF EXISTS pg_temp._remitos;
CREATE TEMP TABLE _remitos AS
SELECT r.*,
       (r.pedido_id IS NOT NULL AND (
            r.fecha_listo IS NULL
         OR (r.fecha_despacho = r.fecha_carga AND r.fecha_recibido = r.fecha_carga)
       )) AS generado
FROM remitos_remito r
WHERE NOT EXISTS (SELECT 1 FROM pedidos_remito_legacy l WHERE l.remito_legacy_id = r.id);

-- ==========================================================================
-- 1) Remitos generados: solo el vínculo.
-- ==========================================================================

INSERT INTO pedidos_remito_legacy (remito_legacy_id, pedido_id)
SELECT id, pedido_id FROM _remitos WHERE generado;

-- ==========================================================================
-- 2) Remitos manuales -> pedidos es_remito = true.
-- ==========================================================================

-- Ids de pedido reservados por adelantado, para poder unir el detalle y el
-- vínculo de vuelta con el remito de origen.
DROP TABLE IF EXISTS pg_temp._map;
CREATE TEMP TABLE _map AS
SELECT id AS remito_id, nextval(pg_get_serial_sequence('pedidos_pedido', 'id')) AS pedido_id
FROM _remitos
WHERE NOT generado;

INSERT INTO pedidos_pedido (
    id, tipo, cliente_id, sucursal_id, origen_sucursal_id, vendedor, estado, es_remito,
    fecha_carga, fecha_entrega, fecha_listo_para_entrega, fecha_entregado, observaciones
)
SELECT
    m.pedido_id,
    CASE r.tipo WHEN 'TRANSFERENCIA' THEN 'SUCURSAL' ELSE 'CLIENTE' END,
    CASE WHEN r.tipo = 'VENTA' THEN r.cliente_id END,
    CASE WHEN r.tipo = 'TRANSFERENCIA' THEN r.destino_sucursal_id END,
    CASE WHEN r.tipo = 'TRANSFERENCIA' THEN r.origen_sucursal_id END,
    COALESCE(r.vendedor, ''),
    CASE WHEN r.fecha_recibido IS NOT NULL THEN 'ENTREGADO' ELSE 'LISTO_PARA_ENTREGA' END,
    true,
    r.fecha_carga,
    COALESCE(r.fecha_recibido, r.fecha_despacho, r.fecha_carga),
    COALESCE(r.fecha_listo, r.fecha_carga),
    r.fecha_recibido,
    LEFT(concat_ws(' | ',
        '[migrado de remitos_remito#' || r.id || ']',
        CASE WHEN r.pedido_id IS NOT NULL THEN '[remito manual del pedido #' || r.pedido_id || ']' END,
        CASE WHEN r.fecha_despacho IS NOT NULL AND r.fecha_recibido IS NULL
             THEN '[en tránsito desde ' || to_char(r.fecha_despacho, 'YYYY-MM-DD HH24:MI') || ']' END,
        NULLIF(r.observaciones, '')
    ), 1000)
FROM _remitos r
JOIN _map m ON m.remito_id = r.id;

INSERT INTO pedidos_pedido_detalle (
    pedido_id, producto_id, cantidad_pedida, cantidad_entregada, cantidad_remitida, observaciones, fecha_creacion
)
SELECT
    m.pedido_id,
    d.producto_id,
    0,
    SUM(d.cantidad),
    0,
    LEFT(string_agg(NULLIF(d.observaciones, ''), ' | ' ORDER BY d.id), 1000),
    MIN(d.fecha_creacion)
FROM remitos_remito_detalle d
JOIN _map m ON m.remito_id = d.remito_id
GROUP BY m.pedido_id, d.producto_id
HAVING SUM(d.cantidad) > 0;

INSERT INTO pedidos_remito_legacy (remito_legacy_id, pedido_id)
SELECT remito_id, pedido_id FROM _map;

-- ==========================================================================
-- 3) Origen de los pedidos SUCURSAL existentes.
-- ==========================================================================

UPDATE pedidos_pedido p
SET origen_sucursal_id = r.origen_sucursal_id
FROM remitos_remito r
WHERE r.pedido_id = p.id
  AND r.tipo = 'TRANSFERENCIA'
  AND p.tipo = 'SUCURSAL'
  AND p.origen_sucursal_id IS NULL;

UPDATE pedidos_pedido p
SET origen_sucursal_id = f.id
FROM (
    SELECT min(id) AS id FROM sucursales_sucursal WHERE tipo = 'FABRICA' HAVING count(*) = 1
) f
WHERE p.tipo = 'SUCURSAL'
  AND p.origen_sucursal_id IS NULL;

-- ==========================================================================
-- 4) Facturación de los pedidos migrados de costos_remitos.
-- ==========================================================================

UPDATE pedidos_pedido p
SET fecha_facturado = cr.fecha_facturacion,
    factura_referencia = 'LEGACY costos_remitos#' || cr.id
FROM costos_remitos cr
WHERE p.fecha_facturado IS NULL
  AND cr.fecha_facturacion IS NOT NULL
  AND substring(p.observaciones FROM '^\[migrado de costos_remitos#(\d+),')::int = cr.id;

-- ==========================================================================
-- 5) Verificación. Lo esperado: 0 remitos sin migrar, ninguna fila de
--    diferencias, unidades origen = destino, 0 pedidos SUCURSAL sin origen.
-- ==========================================================================

SELECT 'remitos sin migrar' AS chequeo, count(*) AS cantidad
FROM remitos_remito r
WHERE NOT EXISTS (SELECT 1 FROM pedidos_remito_legacy l WHERE l.remito_legacy_id = r.id);

-- Remitos generados (vinculados al mismo pedido que referencian) contra
-- cantidad_remitida: una fila acá es un remito mal clasificado o un dato
-- inconsistente previo.
SELECT 'diferencia remitido vs remitos generados' AS chequeo,
       pd.pedido_id, pd.producto_id, pd.cantidad_remitida, COALESCE(g.total, 0) AS total_remitos
FROM pedidos_pedido_detalle pd
LEFT JOIN (
    SELECT r.pedido_id, d.producto_id, SUM(d.cantidad) AS total
    FROM remitos_remito r
    JOIN remitos_remito_detalle d ON d.remito_id = r.id
    JOIN pedidos_remito_legacy l ON l.remito_legacy_id = r.id AND l.pedido_id = r.pedido_id
    GROUP BY r.pedido_id, d.producto_id
) g ON g.pedido_id = pd.pedido_id AND g.producto_id = pd.producto_id
WHERE pd.cantidad_remitida <> COALESCE(g.total, 0)
ORDER BY pd.pedido_id, pd.producto_id;

SELECT 'unidades remitos manuales' AS chequeo,
       (SELECT COALESCE(SUM(d.cantidad), 0)
          FROM remitos_remito_detalle d
          JOIN pedidos_remito_legacy l ON l.remito_legacy_id = d.remito_id
          JOIN pedidos_pedido p ON p.id = l.pedido_id AND p.es_remito) AS origen,
       (SELECT COALESCE(SUM(pd.cantidad_entregada), 0)
          FROM pedidos_pedido_detalle pd
          JOIN pedidos_pedido p ON p.id = pd.pedido_id AND p.es_remito
          JOIN pedidos_remito_legacy l ON l.pedido_id = p.id) AS destino;

SELECT 'pedidos SUCURSAL sin origen' AS chequeo, count(*) AS cantidad
FROM pedidos_pedido
WHERE tipo = 'SUCURSAL' AND origen_sucursal_id IS NULL;
