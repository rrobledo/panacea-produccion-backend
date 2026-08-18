-- pedido-sucursal: permite que un Pedido sea solicitado por una Sucursal en
-- vez de un Cliente, igual que Remito ya distingue tipo=VENTA/TRANSFERENCIA
-- (app/schemas/remito.py::_RemitoTipoFieldsMixin). tipo=CLIENTE (default,
-- compatibilidad con filas existentes) requiere cliente_id; tipo=SUCURSAL
-- requiere sucursal_id y cliente_id debe quedar null — validado a nivel
-- Pydantic (app/schemas/pedido.py), no acá, mismo criterio que Remito.
--
-- Idempotente: seguro de re-ejecutar. Uso previsto:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "BEGIN;" -f migrations/0022_pedido_sucursal.sql -c "ROLLBACK;"   -- dry run
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 -f migrations/0022_pedido_sucursal.sql                          -- apply for real

ALTER TABLE pedidos_pedido ADD COLUMN IF NOT EXISTS tipo VARCHAR(20) NOT NULL DEFAULT 'CLIENTE';
ALTER TABLE pedidos_pedido ADD COLUMN IF NOT EXISTS sucursal_id BIGINT REFERENCES sucursales_sucursal(id);

CREATE INDEX IF NOT EXISTS pedidos_pedido_sucursal_id_idx ON pedidos_pedido (sucursal_id);
