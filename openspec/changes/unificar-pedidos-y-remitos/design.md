## Context

El change `pedidos-y-remitos` separó el Pedido (lo que el cliente o la sucursal pide, con `cantidad_pedida`/`cantidad_entregada` por línea) del Remito (el documento de despacho, `VENTA` o `TRANSFERENCIA`, con su propia máquina de estados `LISTO → EN_TRANSITO → RECIBIDO`). Un remito se crea de dos formas:

1. **Generado** por `pedido_service._generar_remito` cuando el pedido llega a `LISTO_PARA_ENTREGA`/`ENTREGADO`. Copia el delta `cantidad_entregada - cantidad_remitida` y nace con `fecha_carga = fecha_listo = fecha_despacho = fecha_recibido`. Los que creó el backfill `scripts/migrate_remitos_to_pedidos_remitos.sql` nacieron con `fecha_listo = NULL`.
2. **Manual** por `POST /remitos`. Nace en `LISTO` (`fecha_listo = fecha_carga`) y `fecha_recibido` se completa recién en una transición posterior. Puede tener `pedido_id` (solo si es `VENTA`).

Desde `0024_detalle_fecha_creacion.sql`, cada línea de detalle conserva su `fecha_creacion` en las ediciones (merge por `producto_id`). Con eso se puede saber qué se agregó después de la carga original, que era uno de los motivos para tener un documento aparte.

Consumidores: backend (`pedido_service`, `remito_service`, `routers/remitos.py`, `routers/pedidos_reportes.py`) y frontend `panacea-mayorista` (`RemitoNuevoPage`, `RemitosListPage`, `RemitoDetailPage`, sección "Remitos generados" de `PedidoDetailPage`). Ningún otro servicio del backend lee `remitos_remito`.

## Goals / Non-Goals

**Goals:**
- Una sola entidad de envío (`pedidos_pedido` + `pedidos_pedido_detalle`) para pedidos, remitos directos y transferencias.
- Registrar la facturación (`fecha_facturado`, `factura_referencia`) en el envío.
- Imprimir el envío como "REMITO" cuando corresponde.
- Migrar el 100 % de los datos actuales de remitos con un script SQL verificable y re-ejecutable.

**Non-Goals:**
- Renombrar las tablas `pedidos_pedido*` a `envios_*`. El nombre "envío" es conceptual y renombrar rompería todo sin beneficio funcional.
- Integración con un sistema de facturación electrónica. `factura_referencia` es texto libre.
- Reconstruir el historial por tramo de las entregas parciales (ver Riesgos).
- Borrar las tablas `remitos_remito*` en este mismo despliegue.

## Decisions

### D1. El pedido absorbe al remito; un remito directo es un pedido con `es_remito = true`
Se agrega `es_remito BOOLEAN NOT NULL DEFAULT false` al header. En un remito directo, `cantidad_pedida = 0` en todas las líneas y lo despachado va en `cantidad_entregada`.
- *Por qué un flag explícito y no inferirlo de "todas las `cantidad_pedida` = 0":* un pedido normal puede terminar con líneas en 0 pedidas (ítems agregados en la entrega), y los reportes de pendientes necesitan un filtro barato e indexable.
- *Alternativa descartada:* mantener `remitos_remito` como vista o entidad liviana que apunte al pedido. No simplifica nada: se sigue manteniendo el doble modelo.

### D2. `tipo` (`CLIENTE`/`SUCURSAL`) + `origen_sucursal_id` cubren `VENTA`/`TRANSFERENCIA`
`VENTA` equivale a `CLIENTE` y `TRANSFERENCIA` a `SUCURSAL`. `sucursal_id` sigue siendo el destino. Se agrega `origen_sucursal_id` (nullable, FK a `sucursales_sucursal`). Si no se informa en un envío `SUCURSAL`, el servicio asigna la única sucursal `FABRICA`: se reutiliza `_get_fabrica_sucursal`, que hoy solo se usa al generar el remito, y se persiste el valor al crear. Validación en Pydantic (`_PedidoTipoFieldsMixin`), igual que hoy: nada de CHECK en la DB.

### D3. Estados: se usan los del pedido y desaparecen los del remito
Un remito directo nace en `LISTO_PARA_ENTREGA` (equivale a `LISTO`) y avanza a `ENTREGADO` (equivale a `RECIBIDO`). `EN_TRANSITO` no tiene equivalente. En la migración, un remito `EN_TRANSITO` pasa a `LISTO_PARA_ENTREGA` y su `fecha_despacho` queda anotada en `observaciones`.
- *Alternativa descartada:* agregar `EN_TRANSITO` a `PedidoEstado`. Hoy nadie consulta remitos en tránsito (el remito generado nace `RECIBIDO`) y sumaría un estado a todos los pedidos. Si hace falta, se agrega después sin migrar datos (Open Questions).

### D4. Se elimina la generación automática y `cantidad_remitida`
`transition_estado` ya no llama a `_generar_remito`. Mantiene una sola validación: para pasar a `LISTO_PARA_ENTREGA` tiene que haber al menos una línea con `cantidad_entregada > 0` (la misma regla de "no hay ninguna entrega registrada" que existía). La aplicación deja de leer y escribir `cantidad_remitida`. La columna se borra en la migración de limpieza (D8).

### D5. Facturación en el header
Se agregan las columnas `fecha_facturado TIMESTAMPTZ NULL` y `factura_referencia VARCHAR(100) NULL`, y el endpoint `PATCH /pedidos/{id}/facturacion` con body `{fecha_facturado, factura_referencia}`.
- Para marcar: hacen falta los dos valores (referencia no vacía tras trim) y el envío tiene que estar en `LISTO_PARA_ENTREGA` o `ENTREGADO`.
- Para desmarcar: los dos valores en `null`.
- Un envío facturado no se puede cancelar, editar ni registrarle entregas.
- *Por qué un endpoint aparte y no `PUT /pedidos/{id}`:* `PUT` solo vale en `PENDIENTE` (o `LISTO_PARA_ENTREGA` para un remito), y la facturación ocurre después.

### D6. Edición
- Pedido (`es_remito = false`): editable o borrable solo en `PENDIENTE` (sin cambios).
- Remito directo: editable o borrable en `LISTO_PARA_ENTREGA` sin facturar. En la edición, el merge por `producto_id` actualiza `cantidad_entregada` (en vez de `cantidad_pedida`) y preserva `fecha_creacion`.

`ensure_pendiente` pasa a llamarse `ensure_editable(pedido)` y concentra las dos reglas.

### D7. Vínculo con los números de remito anteriores: tabla `pedidos_remito_legacy`
`pedidos_remito_legacy (remito_legacy_id BIGINT PK, pedido_id BIGINT NOT NULL FK ON DELETE CASCADE)`.
- *Por qué una tabla y no una columna en el header:* un pedido con entregas parciales pudo generar varios remitos, y cada número impreso tiene que seguir encontrándose. La PK además hace idempotente la migración.

El listado acepta `remito_legacy_id` y `PedidoRead` expone `remitos_legacy_ids: list[int]`. Los envíos nuevos usan su propio `id` como número de remito.

### D8. Migración en tres piezas
1. `migrations/0033_unificar_pedidos_remitos.sql` (+ `docker/init-db/37_unificar_pedidos_remitos.sql`): esquema aditivo e idempotente.
2. `scripts/migrate_remitos_to_pedidos_unificados.sql`: datos, idempotente, con bloque de verificación final.
3. `migrations/0034_drop_remitos.sql`: limpieza (DROP de `remitos_remito*` y de `cantidad_remitida`). **Se aplica en un despliegue posterior**, una vez validada la verificación.

Clasificación de cada remito en el script:
- **Generado (se absorbe):** `pedido_id IS NOT NULL` y (`fecha_listo IS NULL`, del backfill, o `fecha_despacho = fecha_carga AND fecha_recibido = fecha_carga`, generado en vivo). Sus cantidades ya están en `pedidos_pedido_detalle.cantidad_entregada`. Solo se registra el vínculo en `pedidos_remito_legacy` y se verifica `SUM(cantidad)` contra `cantidad_remitida`.
- **Manual (se convierte):** todo lo demás. Pasa a un pedido `es_remito = true` nuevo. Si tenía `pedido_id`, se anota en `observaciones` (`[remito manual del pedido #N]`). Las líneas se agrupan por `producto_id` (`SUM(cantidad)`, `MIN(fecha_creacion)`) porque el merge por producto del servicio no admite duplicados.

Borrador del SQL (pieza 1):

```sql
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
```

Borrador del SQL (pieza 2):

```sql
-- Uso:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "BEGIN;" -f scripts/migrate_remitos_to_pedidos_unificados.sql -c "ROLLBACK;"   -- dry run
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 -f scripts/migrate_remitos_to_pedidos_unificados.sql                          -- real

DROP TABLE IF EXISTS _remitos;
CREATE TEMP TABLE _remitos AS
SELECT r.*,
       (r.pedido_id IS NOT NULL AND (
            r.fecha_listo IS NULL
         OR (r.fecha_despacho = r.fecha_carga AND r.fecha_recibido = r.fecha_carga)
       )) AS generado
FROM remitos_remito r
WHERE NOT EXISTS (SELECT 1 FROM pedidos_remito_legacy l WHERE l.remito_legacy_id = r.id);

-- 1) Remitos generados: solo vínculo.
INSERT INTO pedidos_remito_legacy (remito_legacy_id, pedido_id)
SELECT id, pedido_id FROM _remitos WHERE generado;

-- 2) Remitos manuales: reservar ids de pedido.
DROP TABLE IF EXISTS _map;
CREATE TEMP TABLE _map AS
SELECT id AS remito_id, nextval(pg_get_serial_sequence('pedidos_pedido', 'id')) AS pedido_id
FROM _remitos WHERE NOT generado;

INSERT INTO pedidos_pedido (
    id, tipo, cliente_id, sucursal_id, origen_sucursal_id, vendedor, estado, es_remito,
    fecha_carga, fecha_entrega, fecha_listo_para_entrega, fecha_entregado, observaciones
)
SELECT m.pedido_id,
       CASE r.tipo WHEN 'TRANSFERENCIA' THEN 'SUCURSAL' ELSE 'CLIENTE' END,
       CASE WHEN r.tipo = 'VENTA' THEN r.cliente_id END,
       CASE WHEN r.tipo = 'TRANSFERENCIA' THEN r.destino_sucursal_id END,
       CASE WHEN r.tipo = 'TRANSFERENCIA' THEN r.origen_sucursal_id END,
       COALESCE(r.vendedor, ''),
       CASE WHEN r.fecha_recibido IS NOT NULL THEN 'ENTREGADO' ELSE 'LISTO_PARA_ENTREGA' END,
       true,
       r.fecha_carga,
       COALESCE(r.fecha_recibido, r.fecha_despacho, r.fecha_carga),
       COALESCE(r.fecha_listo, r.fecha_carga),
       r.fecha_recibido,
       LEFT(NULLIF(concat_ws(' | ',
            '[migrado de remitos_remito#' || r.id || ']',
            CASE WHEN r.pedido_id IS NOT NULL THEN '[remito manual del pedido #' || r.pedido_id || ']' END,
            CASE WHEN r.fecha_despacho IS NOT NULL AND r.fecha_recibido IS NULL
                 THEN '[en tránsito desde ' || to_char(r.fecha_despacho, 'YYYY-MM-DD HH24:MI') || ']' END,
            NULLIF(r.observaciones, '')
       ), ''), 1000)
FROM _remitos r JOIN _map m ON m.remito_id = r.id;

INSERT INTO pedidos_pedido_detalle (
    pedido_id, producto_id, cantidad_pedida, cantidad_entregada, cantidad_remitida, observaciones, fecha_creacion
)
SELECT m.pedido_id, d.producto_id, 0, SUM(d.cantidad), 0,
       LEFT(string_agg(NULLIF(d.observaciones, ''), ' | '), 1000),
       MIN(d.fecha_creacion)
FROM remitos_remito_detalle d JOIN _map m ON m.remito_id = d.remito_id
GROUP BY m.pedido_id, d.producto_id
HAVING SUM(d.cantidad) > 0;

INSERT INTO pedidos_remito_legacy (remito_legacy_id, pedido_id)
SELECT remito_id, pedido_id FROM _map;

-- 3) Origen de los pedidos SUCURSAL existentes: el del remito generado, si no la fábrica única.
UPDATE pedidos_pedido p SET origen_sucursal_id = r.origen_sucursal_id
FROM remitos_remito r
WHERE r.pedido_id = p.id AND r.tipo = 'TRANSFERENCIA'
  AND p.tipo = 'SUCURSAL' AND p.origen_sucursal_id IS NULL;

UPDATE pedidos_pedido p SET origen_sucursal_id = f.id
FROM (SELECT min(id) AS id FROM sucursales_sucursal WHERE tipo = 'FABRICA'
      HAVING count(*) = 1) f
WHERE p.tipo = 'SUCURSAL' AND p.origen_sucursal_id IS NULL;

-- 4) Facturación de los pedidos migrados del legacy.
UPDATE pedidos_pedido p
SET fecha_facturado = cr.fecha_facturacion,
    factura_referencia = 'LEGACY costos_remitos#' || cr.id
FROM costos_remitos cr
WHERE p.fecha_facturado IS NULL
  AND cr.fecha_facturacion IS NOT NULL
  AND substring(p.observaciones FROM '^\[migrado de costos_remitos#(\d+),')::int = cr.id;

-- 5) Verificación.
SELECT 'remitos sin migrar' AS chequeo, count(*) FROM remitos_remito r
 WHERE NOT EXISTS (SELECT 1 FROM pedidos_remito_legacy l WHERE l.remito_legacy_id = r.id);

SELECT 'diferencia remitido vs remitos generados' AS chequeo, pd.pedido_id, pd.producto_id,
       pd.cantidad_remitida, COALESCE(g.total, 0) AS total_remitos
FROM pedidos_pedido_detalle pd
LEFT JOIN (
    SELECT r.pedido_id, d.producto_id, SUM(d.cantidad) AS total
    FROM remitos_remito r
    JOIN remitos_remito_detalle d ON d.remito_id = r.id
    JOIN pedidos_remito_legacy l ON l.remito_legacy_id = r.id AND l.pedido_id = r.pedido_id
    GROUP BY r.pedido_id, d.producto_id
) g ON g.pedido_id = pd.pedido_id AND g.producto_id = pd.producto_id
WHERE pd.cantidad_remitida <> COALESCE(g.total, 0);

SELECT 'unidades remitos manuales' AS chequeo,
       (SELECT COALESCE(SUM(d.cantidad), 0) FROM remitos_remito_detalle d
          JOIN pedidos_remito_legacy l ON l.remito_legacy_id = d.remito_id
          JOIN pedidos_pedido p ON p.id = l.pedido_id AND p.es_remito) AS origen,
       (SELECT COALESCE(SUM(cantidad_entregada), 0) FROM pedidos_pedido_detalle pd
          JOIN pedidos_pedido p ON p.id = pd.pedido_id AND p.es_remito) AS destino;

SELECT 'pedidos SUCURSAL sin origen' AS chequeo, count(*) FROM pedidos_pedido
 WHERE tipo = 'SUCURSAL' AND origen_sucursal_id IS NULL;
```

La idempotencia sale de excluir en `_remitos` lo que ya está en `pedidos_remito_legacy`, de los `UPDATE` que solo tocan valores `NULL` y de los `IF NOT EXISTS` del esquema. El chequeo "diferencia remitido vs remitos generados" no se filtra por corrida, así que vale igual en una re-ejecución.

### D9. Frontend
- `RemitoNuevoPage` hace `pedidosService.create({ es_remito: true, tipo, cliente_id | sucursal_id, origen_sucursal_id, detalles: [{ producto_id, cantidad_pedida: 0, cantidad_entregada }] })` y navega a `/pedidos/:id`.
- `RemitosListPage` usa `pedidosService.list({ es_remito: true })` y muestra la facturación.
- `RemitoDetailPage` se elimina. `/remitos/:id` pasa a ser un redirect que resuelve `?remito_legacy_id=:id` y navega a `/pedidos/:pedidoId`, para los links y números viejos.
- El componente `RemitoCopy` se mueve a `components/remitos/EnvioPrint.jsx`. Recibe el envío y un modo `REMITO`/`PEDIDO` (regla de la spec "Impresión del envío como remito") y `PedidoDetailPage` lo usa con `window.print()`.
- `PedidoDetailPage` quita "Remitos generados" y agrega el bloque "Facturación" (fecha y referencia, con Guardar y Quitar).

## Risks / Trade-offs

- **[Se pierde el detalle por tramo de las entregas parciales]**: antes, cada avance generaba un remito con el delta. Ahora el envío solo guarda el acumulado `cantidad_entregada`, y al imprimir sale el acumulado. → Los remitos legacy siguen vinculados por `pedidos_remito_legacy` y las tablas viejas quedan como archivo hasta la limpieza. Si hace falta imprimir tramos, el operador carga un remito directo por la diferencia.
- **[Heurística de "generado vs manual"]**: depende de las marcas de tiempo que dejaron `_generar_remito` y el backfill. → El chequeo de diferencias contra `cantidad_remitida` detecta cualquier mala clasificación antes del commit (correr el dry run primero).
- **[`EN_TRANSITO` desaparece]**: los remitos en tránsito al migrar quedan en `LISTO_PARA_ENTREGA` con una nota. → Bajo impacto, porque ningún flujo actual depende de ese estado.
- **[Contrato de API roto para `panacea-mayorista`]**: hay que desplegar backend y frontend juntos. → Mismo release. Las tablas viejas se mantienen, así que el rollback es volver al deploy anterior.
- **[Números de remito]**: los envíos nuevos usan el id del pedido, que puede chocar visualmente con números de remito viejos. → El impreso dice "REMITO N° <id>" y los viejos se buscan por `remito_legacy_id`. Ver Open Questions.
- **[Concurrencia en la migración]**: si se crean remitos durante la migración, quedan afuera. → Ejecutarla con la app nueva ya desplegada (que no crea remitos) o en una ventana sin operación. Una re-ejecución levanta los faltantes.

## Migration Plan

1. Backup de `pedidos_pedido*` y `remitos_remito*`.
2. Aplicar `migrations/0033_unificar_pedidos_remitos.sql`. Es aditiva y la app vieja la tolera.
3. Desplegar backend y frontend nuevos juntos.
4. Dry run de `scripts/migrate_remitos_to_pedidos_unificados.sql` (`BEGIN … ROLLBACK`) y revisión de las consultas de verificación (sin filas de diferencia y unidades origen = destino).
5. Ejecución real (`-1`).
6. Después de un período de validación, aplicar `migrations/0034_drop_remitos.sql`.

**Rollback** antes del paso 6: volver al deploy anterior. Las filas `es_remito = true` creadas por la migración o por el uso nuevo se pueden borrar (`DELETE FROM pedidos_pedido WHERE es_remito`), y las columnas nuevas son ignoradas por el código viejo.

## Open Questions

- ¿Hace falta conservar un estado `EN_TRANSITO` para las transferencias entre sucursales? Por defecto no.
- ¿La numeración del remito impreso debe ser una secuencia propia (talonario) en lugar del id del envío? Por defecto, el id.
- ¿`factura_referencia` debe validar un formato (`A-0001-00001234`)? Por defecto, texto libre de hasta 100 caracteres.
