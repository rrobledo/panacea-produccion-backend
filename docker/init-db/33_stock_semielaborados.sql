-- masa-procesos-y-maquinaria F2b (task 3.1): el ledger de stock deja de ser
-- sólo de insumos y pasa a cubrir artículos producidos — ver
-- openspec/changes/masa-procesos-y-maquinaria/{design.md D4, specs/stock/spec.md}
-- en el repo `panacea-produccion`.
--
-- Hasta ahora `stock_movimientos.insumo_id` era NOT NULL: el ledger sólo sabía
-- de materia prima. Con la masa como artículo de pleno derecho hace falta que
-- un movimiento pueda referirse a un producto — un semielaborado que se amasó
-- hoy y se usa mañana, o el sobrante de un redondeo a lote.
--
-- `insumo_id` XOR `producto_id`, igual que en `procesos_proceso_linea`: un
-- movimiento es de un artículo, y los artículos viven en dos tablas.
--
-- Tipos de movimiento después de esta migración:
--   RESERVA          insumo   comprometido por una orden ASIGNADA
--   CONSUMO          insumo   retiro físico al pasar a EN_PRODUCCION
--   AJUSTE           insumo   corrección manual
--   PRODUCCION       producto lo que una orden finalizada fabricó
--   CONSUMO_INTERNO  producto lo que otro proceso consumió de ese stock
--
-- Idempotente: seguro de re-ejecutar. Uso previsto:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "BEGIN;" -f migrations/0029_stock_semielaborados.sql -c "ROLLBACK;"   -- dry run
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 -f migrations/0029_stock_semielaborados.sql                          -- apply for real

ALTER TABLE stock_movimientos ALTER COLUMN insumo_id DROP NOT NULL;
ALTER TABLE stock_movimientos ADD COLUMN IF NOT EXISTS producto_id INTEGER REFERENCES costos_productos(id);
CREATE INDEX IF NOT EXISTS stock_movimientos_producto_id_idx ON stock_movimientos (producto_id);

-- Las filas que ya existen tienen insumo_id cargado y producto_id en NULL, así
-- que satisfacen el XOR sin necesidad de tocarlas.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'stock_movimientos_articulo_xor'
    ) THEN
        ALTER TABLE stock_movimientos ADD CONSTRAINT stock_movimientos_articulo_xor CHECK (
            (insumo_id IS NOT NULL AND producto_id IS NULL)
            OR (insumo_id IS NULL AND producto_id IS NOT NULL)
        );
    END IF;
END $$;
