-- crm-comercial-integrado: adds the commercial roles used to gate CRM
-- endpoints to the existing `user_role` enum. Purely additive — no
-- existing value is renamed or removed, and no existing row changes.
-- See openspec/changes/crm-comercial-integrado/design.md ("Roles: ampliar
-- el enum user_role existente").
--
-- Note: ALTER TYPE ... ADD VALUE cannot be used in the same transaction
-- that later reads/inserts the new value (Postgres limitation) — this
-- migration only adds values, nothing else, so it is safe to apply with
-- either the dry-run or the single-transaction apply flow below.
--
-- Idempotent: safe to re-run (IF NOT EXISTS on each value). Intended usage:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "BEGIN;" -f migrations/0009_crm_roles.sql -c "ROLLBACK;"   -- dry run
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 -f migrations/0009_crm_roles.sql                          -- apply for real

ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'gerencia';
ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'marketing';
ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'supervisor_comercial';
ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'vendedor';
