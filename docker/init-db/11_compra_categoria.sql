-- Mirrors migrations/0007_compra_categoria.sql for local Postgres
-- (docker-compose). See
-- openspec/changes/redesign-cuenta-corriente-proveedor/design.md.

ALTER TABLE compras_compra
    ADD COLUMN IF NOT EXISTS categoria VARCHAR(250) NOT NULL DEFAULT 'MATERIA_PRIMA';

ALTER TABLE compras_pago
    DROP COLUMN IF EXISTS categoria;
