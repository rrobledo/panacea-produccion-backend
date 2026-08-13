-- remito-sin-en-preparacion: el remito deja de tener el paso EN_PREPARACION
-- (nace directo en LISTO, fecha_listo se setea al crear). La columna
-- fecha_preparacion queda sin uso — ver
-- openspec/changes/pedidos-y-remitos/specs/remitos/spec.md.
--
-- Idempotente: seguro de re-ejecutar. Uso previsto:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "BEGIN;" -f migrations/0020_remito_sin_en_preparacion.sql -c "ROLLBACK;"   -- dry run
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 -f migrations/0020_remito_sin_en_preparacion.sql                          -- apply for real

ALTER TABLE remitos_remito DROP COLUMN IF EXISTS fecha_preparacion;
