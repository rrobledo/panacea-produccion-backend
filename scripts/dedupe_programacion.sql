-- One-time reconciliation: colapsa las filas duplicadas de
-- `costos_programacion` a una sola por (producto_id, fecha).
--
-- Ver openspec/changes/masa-procesos-y-maquinaria/{design.md, tasks.md 1.5}
-- en el repo `panacea-produccion`, y la spec `planning-programacion` de ese
-- change.
--
-- Uso:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "BEGIN;" -f scripts/dedupe_programacion.sql -c "ROLLBACK;"   -- dry run
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 -f scripts/dedupe_programacion.sql                          -- apply for real
--
-- En dry run los SELECT de reporte se imprimen igual y la transacción se
-- revierte al final, así que lo listado es exactamente lo que pasaría.
--
-- Por qué hace falta: el modelo siempre asumió una fila por (producto_id,
-- fecha) — programacion_service pivotea a columnas AAAAMMDD-P / AAAAMMDD-E
-- sobre esa premisa — pero nada lo garantizaba. Con duplicados, el pivot
-- conserva en silencio una sola de las filas y el Ejecutado que escribe la
-- finalización de una orden puede caer en la fila equivocada.
-- migrations/0027_programacion_producto_fecha_unico.sql pone el índice único y
-- falla si todavía quedan duplicados, así que este script corre primero.
--
-- Criterio de fusión (spec `planning-programacion`, escenario "Reconciliación
-- de duplicados existentes"): se conserva la fila de menor `id` y se le suman
-- `plan` y `prod` de las demás, que se borran. `responsable` y
-- `producto_nombre` quedan los de la fila conservada.
--
-- Sobre los NULL: SUM() ignora los NULL y devuelve NULL si todas las filas lo
-- eran, que es justo la semántica buscada — NULL significa "sin dato", no
-- cero, y no hay que inventar un 0 donde nadie cargó nada.
--
-- Lo que este script NO hace: no toca las filas con `producto_id` o `fecha` en
-- NULL. No son programación real y el índice único las excluye a propósito.

-- ── Reporte previo: qué se va a fusionar ────────────────────────────────────

SELECT 'grupo_duplicado' AS reporte,
       producto_id,
       fecha,
       COUNT(*)                      AS filas,
       MIN(id)                       AS fila_conservada,
       array_agg(id ORDER BY id)     AS filas_del_grupo,
       array_agg(plan ORDER BY id)   AS planes,
       SUM(plan)                     AS plan_resultante,
       array_agg(prod ORDER BY id)   AS ejecutados,
       SUM(prod)                     AS prod_resultante
  FROM costos_programacion
 WHERE producto_id IS NOT NULL
   AND fecha IS NOT NULL
 GROUP BY producto_id, fecha
HAVING COUNT(*) > 1
 ORDER BY producto_id, fecha;

-- Filas que no parecen el mismo dato repetido sino dos programaciones
-- distintas del mismo producto y fecha. Se fusionan igual, conservando el
-- responsable de la fila de menor id, pero merecen una mirada humana.

SELECT 'responsables_distintos' AS reporte,
       producto_id,
       fecha,
       array_agg(DISTINCT responsable) AS responsables
  FROM costos_programacion
 WHERE producto_id IS NOT NULL
   AND fecha IS NOT NULL
 GROUP BY producto_id, fecha
HAVING COUNT(*) > 1
   AND COUNT(DISTINCT responsable) > 1
 ORDER BY producto_id, fecha;

-- ── Fusión ──────────────────────────────────────────────────────────────────

-- 1. La fila conservada absorbe la suma de plan y prod del grupo.
WITH grupos AS (
    SELECT producto_id,
           fecha,
           MIN(id)   AS conservada,
           SUM(plan) AS plan_total,
           SUM(prod) AS prod_total
      FROM costos_programacion
     WHERE producto_id IS NOT NULL
       AND fecha IS NOT NULL
     GROUP BY producto_id, fecha
    HAVING COUNT(*) > 1
)
UPDATE costos_programacion cp
   SET plan = g.plan_total,
       prod = g.prod_total
  FROM grupos g
 WHERE cp.id = g.conservada;

-- 2. Las demás se borran. El ON DELETE SET NULL de
--    ordenes_produccion_producto_linea.programacion_id (migración 0026) se
--    encarga de las órdenes que apuntaran a una fila borrada: pierden el
--    puntero de procedencia, no la orden.
WITH grupos AS (
    SELECT producto_id,
           fecha,
           MIN(id) AS conservada
      FROM costos_programacion
     WHERE producto_id IS NOT NULL
       AND fecha IS NOT NULL
     GROUP BY producto_id, fecha
    HAVING COUNT(*) > 1
)
DELETE FROM costos_programacion cp
 USING grupos g
 WHERE cp.producto_id = g.producto_id
   AND cp.fecha       = g.fecha
   AND cp.id         <> g.conservada;

-- ── Verificación ────────────────────────────────────────────────────────────

-- Tiene que devolver cero filas: si devuelve alguna, el índice único de la
-- migración 0027 va a fallar al crearse.
SELECT 'duplicados_restantes' AS reporte,
       producto_id,
       fecha,
       COUNT(*) AS filas
  FROM costos_programacion
 WHERE producto_id IS NOT NULL
   AND fecha IS NOT NULL
 GROUP BY producto_id, fecha
HAVING COUNT(*) > 1
 ORDER BY producto_id, fecha;
