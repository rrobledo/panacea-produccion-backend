-- unificar-pedidos-y-remitos: el Pedido pasa a ser la única entidad de
-- envío. Un remito cargado directamente es un pedido con es_remito = true
-- (cantidad_pedida = 0, lo despachado en cantidad_entregada); tipo
-- CLIENTE/SUCURSAL + origen_sucursal_id cubren lo que antes era
-- VENTA/TRANSFERENCIA. Ver
-- openspec/changes/unificar-pedidos-y-remitos/design.md (D1, D2, D5, D7).
--
-- Puramente aditiva: remitos_remito/remitos_remito_detalle y
-- pedidos_pedido_detalle.cantidad_remitida NO se tocan acá — quedan como
-- archivo de solo lectura que lee
-- scripts/migrate_remitos_to_pedidos_unificados.sql, y se borran recién en
-- 0034_drop_remitos.sql, en un despliegue posterior.
--
-- pedidos_remito_legacy vincula cada número de remito ya impreso con el
-- envío que lo reemplaza (un pedido con entregas parciales pudo generar
-- varios remitos, por eso es una tabla y no una columna).
--
-- Idempotente. Uso previsto:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "BEGIN;" -f migrations/0033_unificar_pedidos_remitos.sql -c "ROLLBACK;"   -- dry run
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 -f migrations/0033_unificar_pedidos_remitos.sql                          -- apply for real

ALTER TABLE pedidos_pedido ADD COLUMN IF NOT EXISTS es_remito BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE pedidos_pedido ADD COLUMN IF NOT EXISTS origen_sucursal_id BIGINT REFERENCES sucursales_sucursal(id);
ALTER TABLE pedidos_pedido ADD COLUMN IF NOT EXISTS fecha_facturado TIMESTAMPTZ;
ALTER TABLE pedidos_pedido ADD COLUMN IF NOT EXISTS factura_referencia VARCHAR(100);

CREATE INDEX IF NOT EXISTS pedidos_pedido_es_remito_idx ON pedidos_pedido (es_remito);
CREATE INDEX IF NOT EXISTS pedidos_pedido_origen_sucursal_id_idx ON pedidos_pedido (origen_sucursal_id);
CREATE INDEX IF NOT EXISTS pedidos_pedido_fecha_facturado_idx ON pedidos_pedido (fecha_facturado);

CREATE TABLE IF NOT EXISTS pedidos_remito_legacy (
    remito_legacy_id  BIGINT PRIMARY KEY,
    pedido_id         BIGINT NOT NULL REFERENCES pedidos_pedido(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS pedidos_remito_legacy_pedido_id_idx ON pedidos_remito_legacy (pedido_id);
