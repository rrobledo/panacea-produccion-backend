-- redesign-cuenta-corriente-proveedor: drops compras_orden_compra.numero.
-- OrdenCompra no longer carries a client-supplied document number — the
-- resource is identified by its own `id`, matching the rest of this
-- change's ID-based resources.
--
-- Idempotent: safe to re-run. Intended usage:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "BEGIN;" -f migrations/0004_drop_orden_compra_numero.sql -c "ROLLBACK;"   -- dry run
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 -f migrations/0004_drop_orden_compra_numero.sql                          -- apply for real

ALTER TABLE compras_orden_compra
    DROP COLUMN IF EXISTS numero;
