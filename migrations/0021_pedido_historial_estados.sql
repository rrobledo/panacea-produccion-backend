-- pedido-historial-estados: agrega una columna de fecha por cada estado
-- del Pedido (EN_PREPARACION, PREPARADO, LISTO_PARA_ENTREGA, ENTREGADO,
-- CANCELADO), para mostrar un historial de estados igual al que ya existe
-- en Remito — ver openspec/changes/pedidos-y-remitos/specs/pedidos/spec.md.
-- Pedido.estado sigue siendo una columna propia (no se deriva de estas
-- fechas, a diferencia de Remito): CANCELADO es una transición lateral que
-- no encaja en una precedencia de timestamps lineal.
--
-- Idempotente: seguro de re-ejecutar. Uso previsto:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "BEGIN;" -f migrations/0021_pedido_historial_estados.sql -c "ROLLBACK;"   -- dry run
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 -f migrations/0021_pedido_historial_estados.sql                          -- apply for real

ALTER TABLE pedidos_pedido ADD COLUMN IF NOT EXISTS fecha_en_preparacion TIMESTAMPTZ;
ALTER TABLE pedidos_pedido ADD COLUMN IF NOT EXISTS fecha_preparado TIMESTAMPTZ;
ALTER TABLE pedidos_pedido ADD COLUMN IF NOT EXISTS fecha_listo_para_entrega TIMESTAMPTZ;
ALTER TABLE pedidos_pedido ADD COLUMN IF NOT EXISTS fecha_entregado TIMESTAMPTZ;
ALTER TABLE pedidos_pedido ADD COLUMN IF NOT EXISTS fecha_cancelado TIMESTAMPTZ;
