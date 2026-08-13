-- Mirrors migrations/0020_remito_sin_en_preparacion.sql for local Postgres
-- (docker-compose).

ALTER TABLE remitos_remito DROP COLUMN IF EXISTS fecha_preparacion;
