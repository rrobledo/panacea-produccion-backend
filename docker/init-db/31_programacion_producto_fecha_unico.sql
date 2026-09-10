-- masa-procesos-y-maquinaria F1 (task 1.6): una sola fila de Programación por
-- producto y fecha.
--
-- El modelo siempre asumió una fila por `(producto_id, fecha)` — el servicio
-- pivotea a columnas `AAAAMMDD-P` / `AAAAMMDD-E` sobre esa premisa — pero nada
-- lo garantizaba, y en producción hay filas duplicadas (26 detectadas en
-- archive/2026-09-07-orden-finalizada-actualiza-programacion/tasks.md:3). Con
-- duplicados, el pivot pierde silenciosamente todas las filas menos una y el
-- ejecutado que escribe la finalización de una orden puede caer en la fila
-- equivocada.
--
-- REQUISITO PREVIO: correr la reconciliación antes que esta migración, o el
-- índice falla al crearse:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "BEGIN;" -f scripts/dedupe_programacion.sql -c "ROLLBACK;"   # dry run
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 -f scripts/dedupe_programacion.sql                          # fusiona de verdad
--
-- Índice parcial: `producto_id` y `fecha` son nullable y Postgres permite
-- múltiples NULL en un índice único, pero excluirlos explícitamente deja claro
-- que las filas sin producto o sin fecha (que existen y no son programación
-- real) quedan fuera de la restricción a propósito.
--
-- Idempotente: seguro de re-ejecutar.

CREATE UNIQUE INDEX IF NOT EXISTS costos_programacion_producto_fecha_key
    ON costos_programacion (producto_id, fecha)
 WHERE producto_id IS NOT NULL AND fecha IS NOT NULL;
