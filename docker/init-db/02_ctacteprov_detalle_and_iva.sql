-- Mirrors migrations/0001_ctacteprov_detalle_and_iva.sql — keep in sync.
-- Duplicated (rather than volume-mounted) because Docker won't let a
-- single-file bind mount target a path inside a directory that's already
-- bind-mounted as a whole (see docker-compose.yml's init-db mount).

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
