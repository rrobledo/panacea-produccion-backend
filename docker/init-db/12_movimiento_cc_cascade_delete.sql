-- Mirrors migrations/0008_movimiento_cc_cascade_delete.sql for local
-- Postgres (docker-compose).

ALTER TABLE compras_movimiento_cc
    DROP CONSTRAINT IF EXISTS compras_movimiento_cc_compra_id_fkey,
    ADD CONSTRAINT compras_movimiento_cc_compra_id_fkey
        FOREIGN KEY (compra_id) REFERENCES compras_compra(id) ON DELETE CASCADE;

ALTER TABLE compras_movimiento_cc
    DROP CONSTRAINT IF EXISTS compras_movimiento_cc_pago_id_fkey,
    ADD CONSTRAINT compras_movimiento_cc_pago_id_fkey
        FOREIGN KEY (pago_id) REFERENCES compras_pago(id) ON DELETE CASCADE;
