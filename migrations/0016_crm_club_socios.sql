-- crm-comercial-integrado: crm-integracion-club-socios capability. Local
-- cache of the external Club de Socios system, refreshed by a cron job —
-- never called synchronously in a user-facing read path (design.md,
-- "Cache local de Club de Socios, refrescada por cron").
--
-- Idempotent: safe to re-run. Intended usage:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "BEGIN;" -f migrations/0016_crm_club_socios.sql -c "ROLLBACK;"   -- dry run
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 -f migrations/0016_crm_club_socios.sql                          -- apply for real

CREATE TABLE IF NOT EXISTS crm_club_socio_cache (
    id             BIGSERIAL PRIMARY KEY,
    contacto_id    BIGINT NOT NULL UNIQUE REFERENCES crm_contacto(id) ON DELETE CASCADE,
    socio_id       VARCHAR(100) NOT NULL,
    categoria      VARCHAR(100),
    puntos         INTEGER,
    fecha_alta     DATE,
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT now()
);
