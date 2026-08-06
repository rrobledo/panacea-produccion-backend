-- Mirrors migrations/0010_crm_auditoria.sql for local Postgres (docker-compose).
-- See openspec/changes/crm-comercial-integrado/design.md.

CREATE TABLE crm_auditoria (
    id             BIGSERIAL PRIMARY KEY,
    entidad        VARCHAR(50) NOT NULL,
    entidad_id     INTEGER NOT NULL,
    campo          VARCHAR(100),
    valor_anterior TEXT,
    valor_nuevo    TEXT,
    usuario_id     BIGINT REFERENCES users(id),
    fecha          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX crm_auditoria_entidad_idx ON crm_auditoria (entidad, entidad_id);
