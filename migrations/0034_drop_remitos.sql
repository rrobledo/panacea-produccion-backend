-- unificar-pedidos-y-remitos, limpieza: borra las tablas de remitos y la
-- columna cantidad_remitida, que la app dejó de usar con
-- 0033_unificar_pedidos_remitos.sql. Ver
-- openspec/changes/unificar-pedidos-y-remitos/design.md (D8, Migration Plan
-- paso 6).
--
-- NO aplicar en el mismo despliegue que 0033: primero correr
-- scripts/migrate_remitos_to_pedidos_unificados.sql en real, revisar su
-- verificación final (0 remitos sin migrar, sin diferencias, unidades
-- origen = destino) y dejar pasar el período de validación. Después de esto
-- el rollback al modelo anterior ya no es posible sin un backup.
--
-- pedidos_remito_legacy se conserva: es lo que permite encontrar un remito
-- impreso por su número anterior.
--
-- Por eso, a diferencia de las demás, esta migración no se copia a
-- docker/init-db/ hasta que se aplique en producción.
--
-- Idempotente. Uso previsto:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "BEGIN;" -f migrations/0034_drop_remitos.sql -c "ROLLBACK;"   -- dry run
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 -f migrations/0034_drop_remitos.sql                          -- apply for real

DROP TABLE IF EXISTS remitos_remito_detalle;
DROP TABLE IF EXISTS remitos_remito;

ALTER TABLE pedidos_pedido_detalle DROP COLUMN IF EXISTS cantidad_remitida;
