-- add-auth-oauth-and-custom: creates the `users` table backing local
-- (email/password) and Google OAuth2 authentication, plus role-based
-- authorization. See
-- openspec/changes/add-auth-oauth-and-custom/design.md for the full
-- rationale. Purely additive — does not touch any existing table.
--
-- Idempotent: safe to re-run. Intended usage:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "BEGIN;" -f migrations/0002_create_users.sql -c "ROLLBACK;"   -- dry run
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 -f migrations/0002_create_users.sql                          -- apply for real (-1 wraps in a single transaction)

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'user_role') THEN
        CREATE TYPE user_role AS ENUM ('admin', 'user');
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS users (
    id             BIGSERIAL PRIMARY KEY,
    email          VARCHAR(255) NOT NULL UNIQUE,
    password_hash  VARCHAR(255),
    role           user_role NOT NULL DEFAULT 'user',
    email_verified BOOLEAN NOT NULL DEFAULT false,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS users_email_idx ON users (email);
