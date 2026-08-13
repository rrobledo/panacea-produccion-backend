-- Mirrors migrations/0021_pedido_historial_estados.sql for local Postgres
-- (docker-compose).

ALTER TABLE pedidos_pedido ADD COLUMN IF NOT EXISTS fecha_en_preparacion TIMESTAMPTZ;
ALTER TABLE pedidos_pedido ADD COLUMN IF NOT EXISTS fecha_preparado TIMESTAMPTZ;
ALTER TABLE pedidos_pedido ADD COLUMN IF NOT EXISTS fecha_listo_para_entrega TIMESTAMPTZ;
ALTER TABLE pedidos_pedido ADD COLUMN IF NOT EXISTS fecha_entregado TIMESTAMPTZ;
ALTER TABLE pedidos_pedido ADD COLUMN IF NOT EXISTS fecha_cancelado TIMESTAMPTZ;
