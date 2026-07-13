-- Mirrors migrations/0004_drop_orden_compra_numero.sql for local Postgres
-- (docker-compose). See
-- openspec/changes/redesign-cuenta-corriente-proveedor/design.md.

ALTER TABLE compras_orden_compra
    DROP COLUMN IF EXISTS numero;
