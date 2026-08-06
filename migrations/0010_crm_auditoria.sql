-- crm-comercial-integrado: crm_auditoria is the audit log for CRM writes
-- (RN-005 "toda interacción queda auditada"). Written from the service
-- layer (not a DB trigger) because it needs the authenticated user, which
-- only exists in the request context. See design.md ("Auditoría a nivel
-- de servicio, no trigger de DB").
--
-- Idempotent: safe to re-run. Intended usage:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "BEGIN;" -f migrations/0010_crm_auditoria.sql -c "ROLLBACK;"   -- dry run
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 -f migrations/0010_crm_auditoria.sql                          -- apply for real

CREATE TABLE IF NOT EXISTS crm_auditoria (
    id             BIGSERIAL PRIMARY KEY,
    entidad        VARCHAR(50) NOT NULL,
    entidad_id     INTEGER NOT NULL,
    campo          VARCHAR(100),
    valor_anterior TEXT,
    valor_nuevo    TEXT,
    usuario_id     BIGINT REFERENCES users(id),
    fecha          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS crm_auditoria_entidad_idx ON crm_auditoria (entidad, entidad_id);
