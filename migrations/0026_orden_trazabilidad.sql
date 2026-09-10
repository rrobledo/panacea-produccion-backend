-- masa-procesos-y-maquinaria F1 (tasks 1.3 y 1.4): trazabilidad de la orden
-- de producción hacia atrás — ver openspec/changes/masa-procesos-y-maquinaria/
-- {design.md, tasks.md} en el repo `panacea-produccion`.
--
-- 1. `ordenes_produccion_producto_linea.programacion_id`
--    La línea guarda hoy `producto_id` pero no de qué fila de Programación
--    salió, y esa ausencia ya causó tres limitaciones aceptadas
--    (borrar-orden-y-generar-pendientes/design.md:42-44 y
--    archive/2026-09-07-orden-finalizada-actualiza-programacion/design.md:97-103):
--    la cobertura se calcula por producto en vez de por fila, el ejecutado se
--    escribe en una sola fila, y no se puede reconciliar orden contra
--    programación. El servicio ya venía calculando este id en el preview
--    (`LineaProductoPreview.programacion_id`) y lo descartaba al persistir.
--    Nullable y ON DELETE SET NULL: es un puntero de procedencia, no una
--    dependencia. Las órdenes ya emitidas no tienen cómo saber su origen, y
--    borrar una fila de Programación no puede invalidar una orden que ya
--    existe — el sistema ya soporta finalizar una orden cuya fila de
--    Programación desapareció, y con un FK restrictivo ese borrado fallaría.
--
-- 2. `stock_movimientos.orden_id`
--    Hasta ahora la orden se referenciaba por el string `referencia = codigo`,
--    así que borrar una orden dejaba movimientos huérfanos si no se los
--    borraba a mano — que es exactamente lo que hace hoy `borrar_orden`.
--    El FK con ON DELETE CASCADE hace estructural esa limpieza, siguiendo el
--    mismo criterio que 0008_movimiento_cc_cascade_delete.sql. `referencia` se
--    mantiene: los AJUSTE la usan para el motivo y no referencian ninguna
--    orden. Su retiro es la tarea 8.5, cuando nadie la lea.
--
-- Idempotente: seguro de re-ejecutar. Uso previsto:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "BEGIN;" -f migrations/0026_orden_trazabilidad.sql -c "ROLLBACK;"   -- dry run
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 -f migrations/0026_orden_trazabilidad.sql                          -- apply for real

ALTER TABLE ordenes_produccion_producto_linea
    ADD COLUMN IF NOT EXISTS programacion_id INTEGER REFERENCES costos_programacion(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS ordenes_produccion_producto_linea_programacion_id_idx
    ON ordenes_produccion_producto_linea (programacion_id);

ALTER TABLE stock_movimientos
    ADD COLUMN IF NOT EXISTS orden_id INTEGER REFERENCES ordenes_produccion(id) ON DELETE CASCADE;
CREATE INDEX IF NOT EXISTS stock_movimientos_orden_id_idx ON stock_movimientos (orden_id);

-- Backfill: los movimientos de RESERVA y CONSUMO llevan el código de la orden
-- en `referencia`. El índice único de `codigo` (0025) garantiza que el match
-- identifique una sola orden. Los AJUSTE no matchean nada y quedan en NULL,
-- que es lo correcto: no salieron de una orden.
UPDATE stock_movimientos m
   SET orden_id = o.id
  FROM ordenes_produccion o
 WHERE m.orden_id IS NULL
   AND m.tipo IN ('RESERVA', 'CONSUMO')
   AND m.referencia = o.codigo;
