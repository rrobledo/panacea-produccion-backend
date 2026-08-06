-- Mirrors migrations/0013_crm_segmentacion.sql for local Postgres (docker-compose).
-- See openspec/changes/crm-comercial-integrado/design.md.

CREATE TABLE crm_segmento (
    id         BIGSERIAL PRIMARY KEY,
    nombre     VARCHAR(255) NOT NULL UNIQUE,
    criterio   JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE crm_contacto_segmento (
    id               BIGSERIAL PRIMARY KEY,
    contacto_id      BIGINT NOT NULL REFERENCES crm_contacto(id) ON DELETE CASCADE,
    segmento_id      BIGINT NOT NULL REFERENCES crm_segmento(id) ON DELETE CASCADE,
    recalculado_en   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (contacto_id, segmento_id)
);
