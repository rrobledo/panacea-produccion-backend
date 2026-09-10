-- masa-procesos-y-maquinaria F4 (tareas 5.7 y 5.8): la orden guarda contra qué
-- receta se emitió y el detalle de la partición.
--
-- `proceso_id` ya existe desde 0028 (se adelantó porque la validación de
-- versionado la necesitaba). Acá se suma la versión, que es lo que permite
-- reimprimir una orden vieja con la receta que realmente usó, y las tres
-- columnas del bloque de partición: cuánta masa consume cada rama, con qué
-- gramaje y cuántos bollos salen.
--
-- Idempotente: seguro de re-ejecutar.

ALTER TABLE ordenes_produccion ADD COLUMN IF NOT EXISTS proceso_version INTEGER;

ALTER TABLE ordenes_produccion_producto_linea ADD COLUMN IF NOT EXISTS masa_kg DOUBLE PRECISION;
ALTER TABLE ordenes_produccion_producto_linea ADD COLUMN IF NOT EXISTS bollos INTEGER;
ALTER TABLE ordenes_produccion_producto_linea ADD COLUMN IF NOT EXISTS gramaje_g DOUBLE PRECISION;

-- Lo que el redondeo a lote dejó de más, para que la orden lo declare en vez de
-- esconderlo (design.md D5).
ALTER TABLE ordenes_produccion ADD COLUMN IF NOT EXISTS masa_requerida DOUBLE PRECISION;
ALTER TABLE ordenes_produccion ADD COLUMN IF NOT EXISTS lote_producido DOUBLE PRECISION;
ALTER TABLE ordenes_produccion ADD COLUMN IF NOT EXISTS masa_desde_stock DOUBLE PRECISION;
