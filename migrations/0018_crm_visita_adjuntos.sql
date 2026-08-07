-- Adjuntos (audio/video/imagen) sobre una Visita, para su posterior análisis.
-- Mismo patrón que compras_compra_adjunto / compras_pago_adjunto: contenido
-- guardado directo en Postgres, no en un object storage externo — ver
-- migrations/0005_adjuntos_db_storage.sql para el precedente.

CREATE TABLE IF NOT EXISTS crm_visita_adjunto (
    id        BIGSERIAL PRIMARY KEY,
    visita_id BIGINT NOT NULL REFERENCES crm_visita(id) ON DELETE CASCADE,
    nombre    VARCHAR(255) NOT NULL,
    contenido BYTEA NOT NULL,
    tipo      VARCHAR(100),
    fecha     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS crm_visita_adjunto_visita_id_idx
    ON crm_visita_adjunto (visita_id);
