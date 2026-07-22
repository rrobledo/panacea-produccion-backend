-- Mirrors migrations/0006_pago_categoria.sql for local Postgres
-- (docker-compose). See
-- openspec/changes/redesign-cuenta-corriente-proveedor/design.md.

ALTER TABLE compras_pago
    ADD COLUMN IF NOT EXISTS categoria VARCHAR(250) NOT NULL DEFAULT 'MATERIA_PRIMA';
