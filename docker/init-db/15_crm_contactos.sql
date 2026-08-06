-- Mirrors migrations/0011_crm_contactos.sql for local Postgres (docker-compose).
-- See openspec/changes/crm-comercial-integrado/design.md.

CREATE TABLE crm_rubro (
    id     BIGSERIAL PRIMARY KEY,
    nombre VARCHAR(150) NOT NULL UNIQUE
);

CREATE TABLE crm_ciudad (
    id     BIGSERIAL PRIMARY KEY,
    nombre VARCHAR(150) NOT NULL UNIQUE
);

CREATE TABLE crm_origen (
    id     BIGSERIAL PRIMARY KEY,
    nombre VARCHAR(150) NOT NULL UNIQUE
);

CREATE TABLE crm_empresa (
    id         BIGSERIAL PRIMARY KEY,
    nombre     VARCHAR(255) NOT NULL,
    cuit       VARCHAR(20),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE crm_vendedor (
    id         BIGSERIAL PRIMARY KEY,
    user_id    BIGINT UNIQUE REFERENCES users(id),
    nombre     VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE crm_contacto (
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

CREATE INDEX crm_contacto_empresa_idx ON crm_contacto (empresa_id);
CREATE INDEX crm_contacto_erp_cliente_idx ON crm_contacto (erp_cliente_id);
