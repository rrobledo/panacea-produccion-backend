-- One-time backfill: costos_productos + costos_costos + producto_base_id -> el
-- grafo de procesos.
--
-- Ver openspec/changes/masa-procesos-y-maquinaria/{design.md, tasks.md 2.4-2.8}
-- en el repo `panacea-produccion`.
--
-- Uso:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "BEGIN;" -f scripts/backfill_grafo_procesos.sql -c "ROLLBACK;"   -- dry run
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 -f scripts/backfill_grafo_procesos.sql                          -- apply for real
--
-- Requisito previo: migrations/0028_grafo_procesos.sql.
--
-- Idempotente: cada INSERT está guardado por un NOT EXISTS sobre el código del
-- proceso o sobre la línea, así que se puede correr varias veces mientras se va
-- cargando el catálogo. Correrlo de nuevo no duplica nada ni pisa gramajes ya
-- relevados.
--
-- ## Qué escribe
--
-- **Campos de artículo (2.4, 2.5)** sobre cada producto:
--
--     naturaleza      is_producto=false -> SEMIELABORADO, true -> TERMINADO
--     unidad_base     unidad_medida GR -> KG, UN -> UN, KG -> KG, ML/LT -> LT
--     vendible        true sólo para TERMINADO habilitado
--     peso_unitario_g NO se toca: es el relevamiento de planta de F3
--
-- **Procesos (2.6, 2.7, 2.8)**, una forma por cada caso del modelo viejo:
--
--     P sin producto_base_id      ELABORACION `ELAB-P{id}`
--                                 ENTRADA = sus filas de costos_costos
--                                 SALIDA  = P, cantidad = lote_produccion
--                                 Es el "caso degenerado" del relevamiento: una
--                                 masa sin hijos y un producto que se hace solo
--                                 tienen exactamente la misma forma.
--
--     M con hijos simples         además DIVISION `DIV-P{id}`
--                                 ENTRADA = M, cantidad = lote_produccion
--                                 SALIDA  = cada hijo, gramaje_g NULL
--
--     C con base y con costos     TRANSFORMACION `TRANS-P{id}`
--                                 ENTRADA = su base + sus propios costos_costos
--                                 SALIDA  = C, gramaje_g NULL
--
-- ## Por qué el último caso no es una línea del DIVISION
--
-- Las tareas 2.7 y 2.8 lo describen más simple: toda fila de costos_costos va
-- como ENTRADA "sobre el proceso del producto que la tenía", y para un hijo ese
-- proceso sería el DIVISION de su base. Pero un DIVISION lo comparten todos los
-- hermanos, así que los insumos propios de uno solo quedarían colgando del
-- proceso entero, como si los consumiera toda la división. Es falso, y no es un
-- error que el relevamiento de F3 vaya a corregir: nadie mira una lista de
-- insumos y deduce a qué rama pertenecía cada uno.
--
-- Un hijo con insumos propios es exactamente el caso 3 del relevamiento —parte
-- de la masa se transforma con algo más antes de partirse— así que se lo modela
-- como TRANSFORMACION, que es la forma que el grafo ya tiene para eso.
--
-- ## Qué NO hace
--
-- - No carga gramaje_g, merma_pct ni minutos_directos: son el relevamiento de
--   planta de F3. Las líneas de salida de un DIVISION o un TRANSFORMACION
--   quedan con cantidad = 0 y gramaje_g = NULL, que es lo que el reporte de
--   pendientes de la tarea 4.5 busca para medir el avance.
-- - No toca costos_costos, producto_base_id ni is_producto: el motor viejo
--   sigue leyéndolos hasta F4. Su retiro es F6.
-- - El código del proceso se arma con el id del producto y no con su `codigo`:
--   `codigo` es VARCHAR(50) igual que el del proceso, así que un prefijo lo
--   desbordaría, y nada garantiza que sea único.

-- ── 2.4 y 2.5 · campos de artículo ──────────────────────────────────────────

UPDATE costos_productos
   SET naturaleza  = CASE WHEN is_producto THEN 'TERMINADO' ELSE 'SEMIELABORADO' END,
       unidad_base = CASE upper(COALESCE(unidad_medida, ''))
                          WHEN 'GR' THEN 'KG'
                          WHEN 'KG' THEN 'KG'
                          WHEN 'LT' THEN 'LT'
                          WHEN 'ML' THEN 'LT'
                          WHEN 'UN' THEN 'UN'
                          ELSE 'UN'
                     END,
       vendible    = (is_producto AND habilitado)
 WHERE naturaleza  IS DISTINCT FROM (CASE WHEN is_producto THEN 'TERMINADO' ELSE 'SEMIELABORADO' END)
    OR unidad_base IS DISTINCT FROM (CASE upper(COALESCE(unidad_medida, ''))
                                          WHEN 'GR' THEN 'KG'
                                          WHEN 'KG' THEN 'KG'
                                          WHEN 'LT' THEN 'LT'
                                          WHEN 'ML' THEN 'LT'
                                          WHEN 'UN' THEN 'UN'
                                          ELSE 'UN'
                                     END)
    OR vendible    IS DISTINCT FROM (is_producto AND habilitado);

-- ── 2.6 · ELABORACION por producto sin base ─────────────────────────────────

INSERT INTO procesos_proceso (
    codigo, version, nombre, tipo, responsable,
    lote_referencia, lote_unidad, minutos_setup, vigente_desde
)
SELECT 'ELAB-P' || p.id,
       1,
       'Elaboracion de ' || p.nombre,
       'ELABORACION',
       COALESCE(NULLIF(p.responsable, ''), 'Todos'),
       COALESCE(NULLIF(p.lote_produccion, 0), 1)::double precision,
       p.unidad_base,
       0,
       CURRENT_DATE
  FROM costos_productos p
 WHERE p.producto_base_id IS NULL
   AND NOT EXISTS (
        SELECT 1 FROM procesos_proceso pr WHERE pr.codigo = 'ELAB-P' || p.id
   );

-- 2.8 · las filas de costos_costos del producto son sus ENTRADA.
INSERT INTO procesos_proceso_linea (proceso_id, rol, insumo_id, cantidad, unidad, orden)
SELECT pr.id,
       'ENTRADA',
       c.insumo_id,
       c.cantidad::double precision,
       i.unidad_medida,
       (row_number() OVER (PARTITION BY c.producto_id ORDER BY c.id))::int - 1
  FROM costos_costos c
  JOIN costos_productos p  ON p.id = c.producto_id
  JOIN procesos_proceso pr ON pr.codigo = 'ELAB-P' || p.id
  LEFT JOIN costos_insumos i ON i.id = c.insumo_id
 WHERE p.producto_base_id IS NULL
   AND NOT EXISTS (
        SELECT 1 FROM procesos_proceso_linea l
         WHERE l.proceso_id = pr.id AND l.rol = 'ENTRADA' AND l.insumo_id = c.insumo_id
   );

-- La SALIDA va después de las entradas, con la cantidad que rinde un lote.
INSERT INTO procesos_proceso_linea (proceso_id, rol, producto_id, cantidad, unidad, orden)
SELECT pr.id,
       'SALIDA',
       p.id,
       COALESCE(NULLIF(p.lote_produccion, 0), 1)::double precision,
       p.unidad_base,
       (SELECT COUNT(*) FROM costos_costos c WHERE c.producto_id = p.id)::int
  FROM costos_productos p
  JOIN procesos_proceso pr ON pr.codigo = 'ELAB-P' || p.id
 WHERE p.producto_base_id IS NULL
   AND NOT EXISTS (
        SELECT 1 FROM procesos_proceso_linea l
         WHERE l.proceso_id = pr.id AND l.rol = 'SALIDA' AND l.producto_id = p.id
   );

-- ── 2.7 · DIVISION por masa con hijos sin insumos propios ───────────────────

INSERT INTO procesos_proceso (
    codigo, version, nombre, tipo, responsable,
    lote_referencia, lote_unidad, minutos_setup, vigente_desde
)
SELECT DISTINCT
       'DIV-P' || b.id,
       1,
       'Division de ' || b.nombre,
       'DIVISION',
       COALESCE(NULLIF(b.responsable, ''), 'Todos'),
       COALESCE(NULLIF(b.lote_produccion, 0), 1)::double precision,
       b.unidad_base,
       0,
       CURRENT_DATE
  FROM costos_productos b
  JOIN costos_productos h ON h.producto_base_id = b.id
 WHERE NOT EXISTS (SELECT 1 FROM costos_costos c WHERE c.producto_id = h.id)
   AND NOT EXISTS (SELECT 1 FROM procesos_proceso pr WHERE pr.codigo = 'DIV-P' || b.id);

-- La ENTRADA del DIVISION es la masa entera.
INSERT INTO procesos_proceso_linea (proceso_id, rol, producto_id, cantidad, unidad, orden)
SELECT pr.id,
       'ENTRADA',
       b.id,
       COALESCE(NULLIF(b.lote_produccion, 0), 1)::double precision,
       b.unidad_base,
       0
  FROM costos_productos b
  JOIN procesos_proceso pr ON pr.codigo = 'DIV-P' || b.id
 WHERE NOT EXISTS (
        SELECT 1 FROM procesos_proceso_linea l
         WHERE l.proceso_id = pr.id AND l.rol = 'ENTRADA' AND l.producto_id = b.id
   );

-- Una SALIDA por hijo simple. cantidad 0 y gramaje_g NULL: cuánta masa consume
-- cada bollo es justamente lo que no existe en el modelo viejo.
INSERT INTO procesos_proceso_linea (proceso_id, rol, producto_id, cantidad, unidad, gramaje_g, orden)
SELECT pr.id,
       'SALIDA',
       h.id,
       0,
       h.unidad_base,
       NULL,
       (row_number() OVER (PARTITION BY h.producto_base_id ORDER BY h.id))::int
  FROM costos_productos h
  JOIN costos_productos b  ON b.id = h.producto_base_id
  JOIN procesos_proceso pr ON pr.codigo = 'DIV-P' || b.id
 WHERE NOT EXISTS (SELECT 1 FROM costos_costos c WHERE c.producto_id = h.id)
   AND NOT EXISTS (
        SELECT 1 FROM procesos_proceso_linea l
         WHERE l.proceso_id = pr.id AND l.rol = 'SALIDA' AND l.producto_id = h.id
   );

-- ── 2.7 bis · TRANSFORMACION por hijo con insumos propios ───────────────────

INSERT INTO procesos_proceso (
    codigo, version, nombre, tipo, responsable,
    lote_referencia, lote_unidad, minutos_setup, vigente_desde
)
SELECT 'TRANS-P' || h.id,
       1,
       'Transformacion de ' || h.nombre,
       'TRANSFORMACION',
       COALESCE(NULLIF(h.responsable, ''), 'Todos'),
       COALESCE(NULLIF(b.lote_produccion, 0), 1)::double precision,
       b.unidad_base,
       0,
       CURRENT_DATE
  FROM costos_productos h
  JOIN costos_productos b ON b.id = h.producto_base_id
 WHERE EXISTS (SELECT 1 FROM costos_costos c WHERE c.producto_id = h.id)
   AND NOT EXISTS (SELECT 1 FROM procesos_proceso pr WHERE pr.codigo = 'TRANS-P' || h.id);

-- Entra la masa base…
INSERT INTO procesos_proceso_linea (proceso_id, rol, producto_id, cantidad, unidad, orden)
SELECT pr.id,
       'ENTRADA',
       b.id,
       COALESCE(NULLIF(b.lote_produccion, 0), 1)::double precision,
       b.unidad_base,
       0
  FROM costos_productos h
  JOIN costos_productos b  ON b.id = h.producto_base_id
  JOIN procesos_proceso pr ON pr.codigo = 'TRANS-P' || h.id
 WHERE NOT EXISTS (
        SELECT 1 FROM procesos_proceso_linea l
         WHERE l.proceso_id = pr.id AND l.rol = 'ENTRADA' AND l.producto_id = b.id
   );

-- …y sus insumos propios, que son los que no podían colgar del DIVISION.
INSERT INTO procesos_proceso_linea (proceso_id, rol, insumo_id, cantidad, unidad, orden)
SELECT pr.id,
       'ENTRADA',
       c.insumo_id,
       c.cantidad::double precision,
       i.unidad_medida,
       (row_number() OVER (PARTITION BY c.producto_id ORDER BY c.id))::int
  FROM costos_costos c
  JOIN costos_productos h  ON h.id = c.producto_id
  JOIN procesos_proceso pr ON pr.codigo = 'TRANS-P' || h.id
  LEFT JOIN costos_insumos i ON i.id = c.insumo_id
 WHERE h.producto_base_id IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM procesos_proceso_linea l
         WHERE l.proceso_id = pr.id AND l.rol = 'ENTRADA' AND l.insumo_id = c.insumo_id
   );

INSERT INTO procesos_proceso_linea (proceso_id, rol, producto_id, cantidad, unidad, gramaje_g, orden)
SELECT pr.id,
       'SALIDA',
       h.id,
       0,
       h.unidad_base,
       NULL,
       (SELECT COUNT(*) FROM costos_costos c WHERE c.producto_id = h.id)::int + 1
  FROM costos_productos h
  JOIN procesos_proceso pr ON pr.codigo = 'TRANS-P' || h.id
 WHERE NOT EXISTS (
        SELECT 1 FROM procesos_proceso_linea l
         WHERE l.proceso_id = pr.id AND l.rol = 'SALIDA' AND l.producto_id = h.id
   );

-- ── Verificación y avisos ───────────────────────────────────────────────────

SELECT 'resumen' AS reporte,
       (SELECT COUNT(*) FROM costos_productos)                                        AS productos,
       (SELECT COUNT(*) FROM procesos_proceso WHERE tipo = 'ELABORACION')             AS procesos_elaboracion,
       (SELECT COUNT(*) FROM procesos_proceso WHERE tipo = 'DIVISION')                AS procesos_division,
       (SELECT COUNT(*) FROM procesos_proceso WHERE tipo = 'TRANSFORMACION')          AS procesos_transformacion,
       (SELECT COUNT(*) FROM procesos_proceso_linea WHERE rol = 'ENTRADA')            AS lineas_entrada,
       (SELECT COUNT(*) FROM procesos_proceso_linea WHERE rol = 'SALIDA')             AS lineas_salida;

-- Un producto sin filas de costos_costos deja su ELABORACION sin ninguna
-- ENTRADA: se puede programar pero no explota a insumos ni se puede costear.
SELECT 'elaboracion_sin_entrada' AS reporte, p.id AS producto_id, p.nombre
  FROM costos_productos p
  JOIN procesos_proceso pr ON pr.codigo = 'ELAB-P' || p.id
 WHERE NOT EXISTS (
        SELECT 1 FROM procesos_proceso_linea l WHERE l.proceso_id = pr.id AND l.rol = 'ENTRADA'
   )
 ORDER BY p.id;

-- Un producto cuyo producto_base_id apunta a un producto que no existe queda
-- fuera del grafo: el modelo viejo lo permitía y conviene que se vea.
SELECT 'base_inexistente' AS reporte, h.id AS producto_id, h.nombre, h.producto_base_id
  FROM costos_productos h
 WHERE h.producto_base_id IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM costos_productos b WHERE b.id = h.producto_base_id)
 ORDER BY h.id;

-- Cuánto falta del relevamiento de gramajes: son las salidas medidas por unidad
-- que el backfill deja en blanco a propósito. Es el camino crítico de F3.
SELECT 'pendiente_de_relevamiento' AS reporte,
       pr.codigo AS proceso,
       p.nombre  AS producto
  FROM procesos_proceso_linea l
  JOIN procesos_proceso pr   ON pr.id = l.proceso_id
  JOIN costos_productos p    ON p.id = l.producto_id
 WHERE l.rol IN ('SALIDA', 'COPRODUCTO')
   AND p.unidad_base = 'UN'
   AND l.gramaje_g IS NULL
   -- Sólo las que de verdad necesitan gramaje. Una salida con `cantidad`
   -- cargada declara cuánto rinde un lote y la explosión la resuelve por regla
   -- de tres: es el caso de los ELABORACION 1:1 que dejó el backfill, y contarlos
   -- como pendientes inflaría el relevamiento con productos que no lo necesitan.
   AND COALESCE(l.cantidad, 0) = 0
   AND pr.vigente_hasta IS NULL
 ORDER BY pr.codigo, p.nombre;
