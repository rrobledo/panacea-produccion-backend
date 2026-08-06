-- crm-comercial-integrado: crm-visitas capability.
--
-- Idempotent: safe to re-run. Intended usage:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "BEGIN;" -f migrations/0014_crm_visitas.sql -c "ROLLBACK;"   -- dry run
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 -f migrations/0014_crm_visitas.sql                          -- apply for real

CREATE TABLE IF NOT EXISTS crm_visita (
    id           BIGSERIAL PRIMARY KEY,
    contacto_id  BIGINT NOT NULL REFERENCES crm_contacto(id),
    vendedor_id  BIGINT NOT NULL REFERENCES crm_vendedor(id),
    fecha        DATE NOT NULL,
    notas        TEXT,
    resultado    VARCHAR(100),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS crm_visita_contacto_idx ON crm_visita (contacto_id);
