-- Mirrors migrations/0012_crm_campanas.sql for local Postgres (docker-compose).
-- See openspec/changes/crm-comercial-integrado/design.md.

CREATE TABLE crm_campana (
    id            BIGSERIAL PRIMARY KEY,
    nombre        VARCHAR(255) NOT NULL,
    fecha_inicio  DATE NOT NULL,
    fecha_fin     DATE,
    objetivo      VARCHAR(500),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE crm_contacto_campana (
    id                BIGSERIAL PRIMARY KEY,
    contacto_id       BIGINT NOT NULL REFERENCES crm_contacto(id) ON DELETE CASCADE,
    campana_id        BIGINT NOT NULL REFERENCES crm_campana(id) ON DELETE CASCADE,
    fecha_asociacion  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (contacto_id, campana_id)
);
