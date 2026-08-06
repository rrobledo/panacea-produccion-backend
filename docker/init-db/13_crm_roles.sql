-- Mirrors migrations/0009_crm_roles.sql for local Postgres (docker-compose).
-- See openspec/changes/crm-comercial-integrado/design.md.

ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'gerencia';
ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'marketing';
ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'supervisor_comercial';
ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'vendedor';
