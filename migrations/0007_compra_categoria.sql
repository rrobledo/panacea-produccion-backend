-- redesign-cuenta-corriente-proveedor: moves `categoria` from compras_pago
-- (added in migrations/0006_pago_categoria.sql) to compras_compra instead.
-- The free-string `categoria` on the legacy costos_cuentacorrienteproveedor
-- table describes the purchase/comprobante (materia prima, servicios,
-- etc.), which maps to Compra in the new model, not to the Pago that
-- settles it — 0006 put it on the wrong side.
--
-- Idempotent: safe to re-run. Intended usage:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "BEGIN;" -f migrations/0007_compra_categoria.sql -c "ROLLBACK;"   -- dry run
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 -f migrations/0007_compra_categoria.sql                          -- apply for real

ALTER TABLE compras_compra
    ADD COLUMN IF NOT EXISTS categoria VARCHAR(250) NOT NULL DEFAULT 'MATERIA_PRIMA';

ALTER TABLE compras_pago
    DROP COLUMN IF EXISTS categoria;
