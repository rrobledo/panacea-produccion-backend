-- crm-comercial-integrado: crm-campanas capability. Contacto_Campaña
-- associations are unique per (contacto, campana) so re-associating the
-- same pair is idempotent (RN-004 / design.md).
--
-- Idempotent: safe to re-run. Intended usage:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "BEGIN;" -f migrations/0012_crm_campanas.sql -c "ROLLBACK;"   -- dry run
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 -f migrations/0012_crm_campanas.sql                          -- apply for real

CREATE TABLE IF NOT EXISTS crm_campana (
    id            BIGSERIAL PRIMARY KEY,
    nombre        VARCHAR(255) NOT NULL,
    fecha_inicio  DATE NOT NULL,
    fecha_fin     DATE,
    objetivo      VARCHAR(500),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS crm_contacto_campana (
    id                BIGSERIAL PRIMARY KEY,
    contacto_id       BIGINT NOT NULL REFERENCES crm_contacto(id) ON DELETE CASCADE,
    campana_id        BIGINT NOT NULL REFERENCES crm_campana(id) ON DELETE CASCADE,
    fecha_asociacion  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (contacto_id, campana_id)
);
