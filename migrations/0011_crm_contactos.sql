-- crm-comercial-integrado: core CRM entities (crm-contactos capability).
-- Contacto.erp_cliente_id is a real FK to clientes(idcliente), nullable —
-- RN-002 (a contact can exist without an ERP link) and RN-003 (the link is
-- set on first purchase) — see design.md ("Contacto.erp_cliente_id es una
-- FK real, nullable"). Vendedor is a CRM profile optionally linked to an
-- existing users row, not a new identity (design.md, "Vendedor es un
-- perfil CRM ligado a users").
--
-- Idempotent: safe to re-run. Intended usage:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "BEGIN;" -f migrations/0011_crm_contactos.sql -c "ROLLBACK;"   -- dry run
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 -f migrations/0011_crm_contactos.sql                          -- apply for real

CREATE TABLE IF NOT EXISTS crm_rubro (
    id     BIGSERIAL PRIMARY KEY,
    nombre VARCHAR(150) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS crm_ciudad (
    id     BIGSERIAL PRIMARY KEY,
    nombre VARCHAR(150) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS crm_origen (
    id     BIGSERIAL PRIMARY KEY,
    nombre VARCHAR(150) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS crm_empresa (
    id         BIGSERIAL PRIMARY KEY,
    nombre     VARCHAR(255) NOT NULL,
    cuit       VARCHAR(20),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS crm_vendedor (
    id         BIGSERIAL PRIMARY KEY,
    user_id    BIGINT UNIQUE REFERENCES users(id),
    nombre     VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS crm_contacto (
    id             BIGSERIAL PRIMARY KEY,
    tipo           VARCHAR(10) NOT NULL,
    nombre         VARCHAR(255) NOT NULL,
    email          VARCHAR(255),
    telefono       VARCHAR(50),
    empresa_id     BIGINT REFERENCES crm_empresa(id),
    rubro_id       BIGINT REFERENCES crm_rubro(id),
    ciudad_id      BIGINT REFERENCES crm_ciudad(id),
    origen_id      BIGINT REFERENCES crm_origen(id),
    erp_cliente_id INTEGER REFERENCES clientes(idcliente),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS crm_contacto_empresa_idx ON crm_contacto (empresa_id);
CREATE INDEX IF NOT EXISTS crm_contacto_erp_cliente_idx ON crm_contacto (erp_cliente_id);
