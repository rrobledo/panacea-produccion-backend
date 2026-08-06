-- crm-comercial-integrado: crm-segmentacion capability. `criterio` is a
-- declarative JSON filter definition; membership (`crm_contacto_segmento`)
-- is materialized by a recompute job/endpoint, not evaluated live on every
-- read — see design.md ("Segmentación dinámica: definición declarativa +
-- materialización por cron").
--
-- Idempotent: safe to re-run. Intended usage:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "BEGIN;" -f migrations/0013_crm_segmentacion.sql -c "ROLLBACK;"   -- dry run
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 -f migrations/0013_crm_segmentacion.sql                          -- apply for real

CREATE TABLE IF NOT EXISTS crm_segmento (
    id         BIGSERIAL PRIMARY KEY,
    nombre     VARCHAR(255) NOT NULL UNIQUE,
    criterio   JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS crm_contacto_segmento (
    id               BIGSERIAL PRIMARY KEY,
    contacto_id      BIGINT NOT NULL REFERENCES crm_contacto(id) ON DELETE CASCADE,
    segmento_id      BIGINT NOT NULL REFERENCES crm_segmento(id) ON DELETE CASCADE,
    recalculado_en   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (contacto_id, segmento_id)
);
