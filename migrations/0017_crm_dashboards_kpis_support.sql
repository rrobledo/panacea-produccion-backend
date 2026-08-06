-- crm-comercial-integrado: crm-dashboards-kpis capability needs two small
-- additive columns that earlier groups didn't need:
--   - crm_campana.costo: campaign spend, required to compute ROI/CAC
--     (SRS section 10) — without a spend figure those KPIs have nothing
--     to divide by.
--   - crm_contacto.observaciones: free-text field shown on the customer
--     360 dashboard (SRS section 14, Anexo "Dashboard Cliente").
--
-- Idempotent: safe to re-run. Intended usage:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "BEGIN;" -f migrations/0017_crm_dashboards_kpis_support.sql -c "ROLLBACK;"   -- dry run
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 -f migrations/0017_crm_dashboards_kpis_support.sql                          -- apply for real

ALTER TABLE crm_campana ADD COLUMN IF NOT EXISTS costo NUMERIC;
ALTER TABLE crm_contacto ADD COLUMN IF NOT EXISTS observaciones TEXT;
