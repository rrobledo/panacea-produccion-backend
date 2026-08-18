-- Mirrors migrations/0022_pedido_sucursal.sql for local Postgres
-- (docker-compose).

ALTER TABLE pedidos_pedido ADD COLUMN IF NOT EXISTS tipo VARCHAR(20) NOT NULL DEFAULT 'CLIENTE';
ALTER TABLE pedidos_pedido ADD COLUMN IF NOT EXISTS sucursal_id BIGINT REFERENCES sucursales_sucursal(id);

CREATE INDEX IF NOT EXISTS pedidos_pedido_sucursal_id_idx ON pedidos_pedido (sucursal_id);
