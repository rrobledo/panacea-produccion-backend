-- redesign-cuenta-corriente-proveedor: adjuntos (Compra and Pago receipt
-- images) move from external object storage (Vercel Blob, a `url` column)
-- to a `contenido BYTEA` column stored directly in Postgres. Adds
-- Pago-scoped attachments (compras_pago_adjunto), which did not exist
-- before.
--
-- NOTE: this does not backfill compras_compra_adjunto.url values into
-- contenido — any row created against Vercel Blob before this migration
-- loses its content and must be re-uploaded. None are expected to exist in
-- any deployed environment yet (this attachment feature is part of the
-- still-unarchived redesign-cuenta-corriente-proveedor change).
--
-- Idempotent: safe to re-run. Intended usage:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "BEGIN;" -f migrations/0005_adjuntos_db_storage.sql -c "ROLLBACK;"   -- dry run
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 -f migrations/0005_adjuntos_db_storage.sql                          -- apply for real

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
