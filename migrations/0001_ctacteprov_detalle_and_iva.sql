-- ctacteprov-detalle-insumos: adds iva/percepcion to
-- costos_cuentacorrienteproveedor and a new 1-to-many detail table for
-- per-insumo invoice breakdown. See
-- openspec/changes/ctacteprov-detalle-insumos/design.md for the full
-- rationale (including why this DDL lives here rather than as a Django
-- migration in panacea-backend).
--
-- Idempotent: safe to re-run. Intended usage:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "BEGIN;" -f migrations/0001_ctacteprov_detalle_and_iva.sql -c "ROLLBACK;"   -- dry run
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 -f migrations/0001_ctacteprov_detalle_and_iva.sql                          -- apply for real (-1 wraps in a single transaction)

ALTER TABLE costos_cuentacorrienteproveedor
    ADD COLUMN IF NOT EXISTS iva DOUBLE PRECISION DEFAULT 0,
    ADD COLUMN IF NOT EXISTS percepcion DOUBLE PRECISION DEFAULT 0;

CREATE TABLE IF NOT EXISTS costos_cuentacorrienteproveedordetalle (
    id                          BIGSERIAL PRIMARY KEY,
    cuentacorrienteproveedor_id BIGINT NOT NULL REFERENCES costos_cuentacorrienteproveedor(id) ON DELETE CASCADE,
    insumo_id                   INTEGER NOT NULL REFERENCES costos_insumos(id) ON DELETE RESTRICT,
    cantidad                    DOUBLE PRECISION NOT NULL,
    subtotal                    DOUBLE PRECISION NOT NULL
);

CREATE INDEX IF NOT EXISTS costos_cuentacorrienteproveedordetalle_cuentacorrienteproveedor_id_idx
    ON costos_cuentacorrienteproveedordetalle (cuentacorrienteproveedor_id);
