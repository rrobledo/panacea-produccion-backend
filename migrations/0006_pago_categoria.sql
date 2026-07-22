-- redesign-cuenta-corriente-proveedor: adds a `categoria` column to
-- compras_pago, mirroring the free-string `categoria` that already exists
-- on the legacy costos_cuentacorrienteproveedor table (default
-- 'MATERIA_PRIMA', no DB-level enum — same non-constraint as the legacy
-- column).
--
-- Idempotent: safe to re-run. Intended usage:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "BEGIN;" -f migrations/0006_pago_categoria.sql -c "ROLLBACK;"   -- dry run
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 -f migrations/0006_pago_categoria.sql                          -- apply for real

ALTER TABLE compras_pago
    ADD COLUMN IF NOT EXISTS categoria VARCHAR(250) NOT NULL DEFAULT 'MATERIA_PRIMA';
