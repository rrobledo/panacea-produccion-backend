-- ordenes-produccion-stock: introduces the stock/production-order domain —
-- see openspec/changes/ordenes-produccion-stock/{proposal,design}.md.
--
-- - `ubicaciones_ubicacion`: flat catalog of depósitos/sectores.
-- - `costos_productos.producto_base_id`: self-referencial link to the
--   intermediate producto (masa) a final producto is built from.
-- - `stock_movimientos`: RESERVA/CONSUMO/AJUSTE ledger for costos_insumos.
-- - `ordenes_produccion` (+ producto/insumo líneas): generated from
--   Programación, ASIGNADA -> EN_PRODUCCION -> FINALIZADA / CANCELADA.
-- - `productos_fabricados`: what actually came out of a finalized orden
--   (cantidad, ubicación, desperdicio).
--
-- Idempotente: seguro de re-ejecutar. Uso previsto:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "BEGIN;" -f migrations/0023_ordenes_produccion_stock.sql -c "ROLLBACK;"   -- dry run
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 -f migrations/0023_ordenes_produccion_stock.sql                          -- apply for real

CREATE TABLE IF NOT EXISTS ubicaciones_ubicacion (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(255) NOT NULL
);

ALTER TABLE costos_productos ADD COLUMN IF NOT EXISTS producto_base_id INTEGER REFERENCES costos_productos(id);
CREATE INDEX IF NOT EXISTS costos_productos_producto_base_id_idx ON costos_productos (producto_base_id);

CREATE TABLE IF NOT EXISTS stock_movimientos (
    id SERIAL PRIMARY KEY,
    insumo_id INTEGER NOT NULL REFERENCES costos_insumos(id),
    tipo VARCHAR(20) NOT NULL,
    cantidad DOUBLE PRECISION NOT NULL,
    referencia VARCHAR(255),
    fecha TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS stock_movimientos_insumo_id_idx ON stock_movimientos (insumo_id);

CREATE TABLE IF NOT EXISTS ordenes_produccion (
    id SERIAL PRIMARY KEY,
    codigo VARCHAR(50) NOT NULL,
    fecha_fabricacion DATE NOT NULL,
    responsable VARCHAR(50) NOT NULL,
    estado VARCHAR(20) NOT NULL DEFAULT 'ASIGNADA',
    fecha_creacion TIMESTAMPTZ NOT NULL,
    fecha_en_produccion TIMESTAMPTZ,
    fecha_finalizada TIMESTAMPTZ,
    fecha_cancelada TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ordenes_produccion_fecha_fabricacion_idx ON ordenes_produccion (fecha_fabricacion);

CREATE TABLE IF NOT EXISTS ordenes_produccion_producto_linea (
    id SERIAL PRIMARY KEY,
    orden_id INTEGER NOT NULL REFERENCES ordenes_produccion(id) ON DELETE CASCADE,
    producto_id INTEGER NOT NULL REFERENCES costos_productos(id),
    cantidad_planeada INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ordenes_produccion_producto_linea_orden_id_idx ON ordenes_produccion_producto_linea (orden_id);

CREATE TABLE IF NOT EXISTS ordenes_produccion_insumo_linea (
    id SERIAL PRIMARY KEY,
    orden_id INTEGER NOT NULL REFERENCES ordenes_produccion(id) ON DELETE CASCADE,
    insumo_id INTEGER NOT NULL REFERENCES costos_insumos(id),
    cantidad DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS ordenes_produccion_insumo_linea_orden_id_idx ON ordenes_produccion_insumo_linea (orden_id);

CREATE TABLE IF NOT EXISTS productos_fabricados (
    id SERIAL PRIMARY KEY,
    orden_id INTEGER NOT NULL REFERENCES ordenes_produccion(id),
    producto_id INTEGER NOT NULL REFERENCES costos_productos(id),
    cantidad_fabricada DOUBLE PRECISION NOT NULL,
    ubicacion_id INTEGER NOT NULL REFERENCES ubicaciones_ubicacion(id),
    cantidad_desperdicio DOUBLE PRECISION NOT NULL DEFAULT 0,
    ubicacion_desperdicio_id INTEGER REFERENCES ubicaciones_ubicacion(id),
    motivo_desperdicio VARCHAR(500),
    fecha TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS productos_fabricados_producto_id_idx ON productos_fabricados (producto_id);
CREATE INDEX IF NOT EXISTS productos_fabricados_ubicacion_id_idx ON productos_fabricados (ubicacion_id);

-- Sembrado de apertura (tasks.md 1.6): un AJUSTE por cada insumo existente
-- igual a su cantidad actual, para no perder el valor al pasar a que
-- insumos.cantidad se derive de stock_movimientos. Solo inserta si el
-- insumo todavía no tiene ningún movimiento (re-ejecutable sin duplicar).
INSERT INTO stock_movimientos (insumo_id, tipo, cantidad, referencia, fecha)
SELECT i.id, 'AJUSTE', i.cantidad, 'Apertura', now()
  FROM costos_insumos i
 WHERE NOT EXISTS (SELECT 1 FROM stock_movimientos m WHERE m.insumo_id = i.id);
