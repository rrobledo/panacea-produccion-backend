-- Mirrors migrations/0016_crm_club_socios.sql for local Postgres (docker-compose).
-- See openspec/changes/crm-comercial-integrado/design.md.

CREATE TABLE crm_club_socio_cache (
    id             BIGSERIAL PRIMARY KEY,
    contacto_id    BIGINT NOT NULL UNIQUE REFERENCES crm_contacto(id) ON DELETE CASCADE,
    socio_id       VARCHAR(100) NOT NULL,
    categoria      VARCHAR(100),
    puntos         INTEGER,
    fecha_alta     DATE,
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT now()
);
