-- Mirrors migrations/0002_create_users.sql for local Postgres (docker-compose).
-- See openspec/changes/add-auth-oauth-and-custom/design.md.

CREATE TYPE user_role AS ENUM ('admin', 'user');

CREATE TABLE users (
    id             BIGSERIAL PRIMARY KEY,
    email          VARCHAR(255) NOT NULL UNIQUE,
    password_hash  VARCHAR(255),
    role           user_role NOT NULL DEFAULT 'user',
    email_verified BOOLEAN NOT NULL DEFAULT false,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX users_email_idx ON users (email);
