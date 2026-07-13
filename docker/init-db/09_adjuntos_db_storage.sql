-- Mirrors migrations/0005_adjuntos_db_storage.sql for local Postgres
-- (docker-compose). See
-- openspec/changes/redesign-cuenta-corriente-proveedor/design.md.

ALTER TABLE compras_compra_adjunto
    DROP COLUMN IF EXISTS url;

ALTER TABLE compras_compra_adjunto
    ADD COLUMN IF NOT EXISTS contenido BYTEA NOT NULL DEFAULT ''::bytea;

ALTER TABLE compras_compra_adjunto
    ALTER COLUMN contenido DROP DEFAULT;

CREATE TABLE IF NOT EXISTS compras_pago_adjunto (
    id        BIGSERIAL PRIMARY KEY,
    pago_id   BIGINT NOT NULL REFERENCES compras_pago(id) ON DELETE CASCADE,
    nombre    VARCHAR(255) NOT NULL,
    contenido BYTEA NOT NULL,
    tipo      VARCHAR(20),
    fecha     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS compras_pago_adjunto_pago_id_idx
    ON compras_pago_adjunto (pago_id);
