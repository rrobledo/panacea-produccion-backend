-- redesign-cuenta-corriente-proveedor: compras_movimiento_cc.compra_id and
-- .pago_id were created (migrations/0003_compras_tesoreria_ordenes.sql)
-- without ON DELETE CASCADE, unlike every other FK pointing at
-- compras_compra/compras_pago. That leaves DELETE /costos/compras/{id} and
-- DELETE /costos/pagos/{id} unusable in practice: every Compra/Pago gets a
-- MovimientoCC row on creation (compra_service.create_compra /
-- pago_service.create_pago, via movimiento_cc_service.append_*_movimiento),
-- so the delete always hits
-- "violates foreign key constraint compras_movimiento_cc_{compra,pago}_id_fkey"
-- and 500s before compras_pago_aplicacion's own ON DELETE CASCADE + the
-- trg_update_compra_saldo_pendiente trigger (which correctly reverts
-- Compra.saldo_pendiente/estado on aplicacion delete) ever get a chance to
-- run. A dangling ledger row for a comprobante/pago that no longer exists
-- would corrupt the running-balance ledger anyway, so cascading the delete
-- (rather than blocking it) is the correct fix, not a workaround.
--
-- Idempotent: safe to re-run. Intended usage:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "BEGIN;" -f migrations/0008_movimiento_cc_cascade_delete.sql -c "ROLLBACK;"   -- dry run
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 -f migrations/0008_movimiento_cc_cascade_delete.sql                          -- apply for real

ALTER TABLE compras_movimiento_cc
    DROP CONSTRAINT IF EXISTS compras_movimiento_cc_compra_id_fkey,
    ADD CONSTRAINT compras_movimiento_cc_compra_id_fkey
        FOREIGN KEY (compra_id) REFERENCES compras_compra(id) ON DELETE CASCADE;

ALTER TABLE compras_movimiento_cc
    DROP CONSTRAINT IF EXISTS compras_movimiento_cc_pago_id_fkey,
    ADD CONSTRAINT compras_movimiento_cc_pago_id_fkey
        FOREIGN KEY (pago_id) REFERENCES compras_pago(id) ON DELETE CASCADE;
