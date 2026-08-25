-- fecha_creacion en el detalle de Pedido y Remito: permite distinguir si un
-- ítem fue agregado al crear el comprobante o añadido después en una edición.
-- Para que esto sea útil, update_pedido/update_remito (app/services/) dejan
-- de borrar y recrear todas las filas de detalle al guardar cambios y en
-- cambio hacen merge por producto_id, preservando fecha_creacion en los
-- ítems que ya existían.
--
-- Idempotente. Uso previsto:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "BEGIN;" -f migrations/0024_detalle_fecha_creacion.sql -c "ROLLBACK;"   -- dry run
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 -f migrations/0024_detalle_fecha_creacion.sql                          -- apply for real

ALTER TABLE pedidos_pedido_detalle ADD COLUMN IF NOT EXISTS fecha_creacion TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE remitos_remito_detalle ADD COLUMN IF NOT EXISTS fecha_creacion TIMESTAMPTZ NOT NULL DEFAULT now();
