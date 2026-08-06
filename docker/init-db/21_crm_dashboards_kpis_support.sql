-- Mirrors migrations/0017_crm_dashboards_kpis_support.sql for local Postgres (docker-compose).
-- See openspec/changes/crm-comercial-integrado/design.md.

ALTER TABLE crm_campana ADD COLUMN costo NUMERIC;
ALTER TABLE crm_contacto ADD COLUMN observaciones TEXT;
