-- crm-comercial-integrado: crm-oportunidades capability. crm_etapa_venta
-- is a small ordered catalog (Lead..Cliente Activo) seeded here so
-- Oportunidad.etapa_id always has somewhere valid to point.
--
-- Idempotent: safe to re-run. Intended usage:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "BEGIN;" -f migrations/0015_crm_oportunidades.sql -c "ROLLBACK;"   -- dry run
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 -f migrations/0015_crm_oportunidades.sql                          -- apply for real

CREATE TABLE IF NOT EXISTS crm_etapa_venta (
    id     BIGSERIAL PRIMARY KEY,
    nombre VARCHAR(50) NOT NULL UNIQUE,
    orden  INTEGER NOT NULL UNIQUE
);

INSERT INTO crm_etapa_venta (nombre, orden) VALUES
    ('Lead', 1),
    ('Visita', 2),
    ('Interesado', 3),
    ('Muestras', 4),
    ('Presupuesto', 5),
    ('Negociacion', 6),
    ('Primera Compra', 7),
    ('Cliente Activo', 8)
ON CONFLICT (nombre) DO NOTHING;

CREATE TABLE IF NOT EXISTS crm_oportunidad (
    id           BIGSERIAL PRIMARY KEY,
    contacto_id  BIGINT NOT NULL REFERENCES crm_contacto(id),
    visita_id    BIGINT REFERENCES crm_visita(id),
    etapa_id     BIGINT NOT NULL REFERENCES crm_etapa_venta(id),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS crm_actividad (
    id              BIGSERIAL PRIMARY KEY,
    oportunidad_id  BIGINT NOT NULL REFERENCES crm_oportunidad(id) ON DELETE CASCADE,
    tipo            VARCHAR(50) NOT NULL,
    fecha           DATE NOT NULL,
    notas           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
