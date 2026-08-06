-- Mirrors migrations/0014_crm_visitas.sql for local Postgres (docker-compose).
-- See openspec/changes/crm-comercial-integrado/design.md.

CREATE TABLE crm_visita (
    id           BIGSERIAL PRIMARY KEY,
    contacto_id  BIGINT NOT NULL REFERENCES crm_contacto(id),
    vendedor_id  BIGINT NOT NULL REFERENCES crm_vendedor(id),
    fecha        DATE NOT NULL,
    notas        TEXT,
    resultado    VARCHAR(100),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX crm_visita_contacto_idx ON crm_visita (contacto_id);
