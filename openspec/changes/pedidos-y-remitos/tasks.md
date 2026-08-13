## 1. Base de datos: sucursales, pedidos, remito rediseñado

- [x] 1.1 `migrations/0019_pedidos_remitos_sucursales.sql` +
      `docker/init-db/23_pedidos_remitos_sucursales.sql` (mismo par
      que las migraciones anteriores): crear `sucursales_sucursal`
      (`id`, `nombre`, `tipo`, `activa`), `pedidos_pedido` (`id`,
      `cliente_id` FK, `vendedor`, `estado`, `fecha_carga`,
      `fecha_entrega`, `observaciones`), `pedidos_pedido_detalle`
      (`id`, `pedido_id` FK, `producto_id` FK, `cantidad_pedida`,
      `cantidad_entregada`, `observaciones`).
- [x] 1.2 En la misma migración: crear `remitos_remito` (`id`, `tipo`,
      `cliente_id` FK nullable, `pedido_id` FK nullable,
      `origen_sucursal_id`/`destino_sucursal_id` FK nullable,
      `vendedor`, `observaciones`, `fecha_carga`, timestamps de estado
      `fecha_preparacion`/`fecha_listo`/`fecha_despacho`/
      `fecha_recibido`) y `remitos_remito_detalle` (`id`, `remito_id`
      FK, `producto_id` FK, `cantidad`, `observaciones`).
      Constraint/check a nivel DB para las combinaciones de campos
      condicionales de `tipo` es opcional (la validación fuerte vive
      en el schema Pydantic); si se agrega, documentar en el propio
      SQL por qué.
- [x] 1.3 Esta migración NO toca `costos_remitos`/
      `costos_remitodetalles` — quedan intactas como archivo histórico
      read-only, fuente del script de backfill del grupo 7 (ver
      design.md Decisión 6). No agregar ningún `DROP TABLE` sobre
      ellas en esta migración.

## 2. Modelo `Sucursal`

- [x] 2.1 `app/models/sucursal.py`: `Sucursal` (id, nombre, tipo,
      activa).
- [x] 2.2 `app/schemas/sucursal.py`: `SucursalCreate`, `SucursalUpdate`,
      `SucursalRead`.
- [x] 2.3 `app/services/sucursal_service.py`: crear, listar (filtros
      `tipo`/`activa`), actualizar.
- [x] 2.4 `app/routers/sucursales.py`: `POST/GET /sucursales`,
      `PUT /sucursales/{id}`. Registrar en `app/main.py`.
- [x] 2.5 Tests: `tests/unit/test_sucursales.py` cubriendo los
      escenarios de `specs/sucursales/spec.md`.

## 3. Modelo `Pedido`

- [x] 3.1 `app/models/pedido.py`: `Pedido`, `PedidoDetalle`
      (`cantidad_pedida`, `cantidad_entregada`), propiedad/columna
      `estado`.
- [x] 3.2 `app/schemas/pedido.py`: `PedidoDetalleCreate`,
      `PedidoDetalleRead`, `PedidoCreate`, `PedidoUpdate`,
      `PedidoRead`, `EstadoTransitionRequest`, request de entrega
      parcial (`PedidoEntregaRequest`: lista de `{detalle_id,
      cantidad_entregada}`).
- [x] 3.3 `app/services/pedido_service.py`: crear, listar/filtrar,
      actualizar (restringido a `PENDIENTE`), borrar (restringido a
      `PENDIENTE`), registrar entrega parcial (valida
      no-decreciente y `<= cantidad_pedida` por línea, según
      `specs/pedidos/spec.md`).
- [x] 3.4 `app/routers/pedidos.py`: `POST/GET /pedidos`,
      `GET/PUT/DELETE /pedidos/{id}`, `PATCH /pedidos/{id}/estado`,
      `PATCH /pedidos/{id}/entrega`. Registrar en `app/main.py`.
- [x] 3.5 Tests: `tests/unit/test_pedidos.py` cubriendo alta, entrega
      parcial y transiciones (sin la generación de remito, que se
      cubre en el grupo 5).

## 4. Modelo `Remito` (rediseñado)

- [x] 4.1 `app/models/remito.py`: `Remito` (con `tipo`, `cliente_id`
      nullable, `pedido_id` nullable, `origen_sucursal_id`/
      `destino_sucursal_id` nullable, timestamps de estado renombrados
      sin `fecha_facturacion`), `RemitoDetalle`.
- [x] 4.2 `app/schemas/remito.py`: `RemitoDetalleCreate/Read`,
      `RemitoCreate`, `RemitoUpdate`, `RemitoRead`,
      `EstadoTransitionRequest`; `model_validator` que aplica las
      reglas condicionales de `tipo` (VENTA requiere `cliente_id` y
      prohíbe sucursales; TRANSFERENCIA requiere ambas sucursales
      distintas y prohíbe `cliente_id`/`pedido_id`) — ver
      `specs/remitos/spec.md`.
- [x] 4.3 `app/services/remito_service.py`: crear, listar/filtrar
      (`tipo`, `cliente_id`, `pedido_id`, `origen_sucursal_id`,
      `destino_sucursal_id`, `estado`, rango de fecha), transición de
      estado (secuencia `PENDIENTE → EN_PREPARACION → LISTO →
      EN_TRANSITO → RECIBIDO`), actualizar/borrar (restringido a
      `PENDIENTE`).
- [x] 4.4 `app/routers/remitos.py` (reescrito desde cero):
      `POST/GET /remitos`, `GET/PUT/DELETE /remitos/{id}`,
      `PATCH /remitos/{id}/estado`. Actualizar el registro en
      `app/main.py` para el router nuevo.
- [x] 4.5 Tests: `tests/unit/test_remitos.py` cubriendo alta (ambos
      tipos, validación de campos condicionales) y transiciones de
      estado.

## 5. Generación automática de remito desde pedido

- [x] 5.1 En `pedido_service.py`, al procesar `PATCH .../estado` hacia
      `LISTO_PARA_ENTREGA`/`ENTREGADO`: calcular por línea el
      incremento de `cantidad_entregada` desde el último remito
      generado para ese pedido, usando la columna
      `PedidoDetalle.cantidad_remitida`. Si no hay ningún incremento:
      rechazar con 422 solo si el pedido nunca generó un remito antes;
      si ya generó al menos uno, completar la transición igual sin
      generar uno nuevo (ver design.md Decisión 3.1 — corregido
      durante la implementación, la versión original rechazaba
      siempre y dejaba trabado cualquier pedido entregado 100% de una
      sola vez).
- [x] 5.2 Crear el `Remito` (`tipo=VENTA`, `pedido_id`, `cliente_id`
      del pedido, una línea por `PedidoDetalle` con incremento) y la
      transición de estado del pedido en la misma transacción;
      cualquier excepción revierte ambas.
- [x] 5.3 Tests: `tests/unit/test_pedido_genera_remito.py` cubriendo
      los escenarios de "Generación automática de remito" en
      `specs/pedidos/spec.md`, incluyendo la segunda tanda de entrega
      generando un segundo remito con solo el incremento, y el caso de
      entrega 100% de una sola vez completando igual la transición a
      `ENTREGADO` sin un segundo remito.

## 6. Retiro del modelo `Remitos` legacy

- [x] 6.1 Eliminar `app/models/remitos.py`, `app/schemas/remitos.py`,
      `app/services/remitos_service.py`, `app/routers/remitos_reportes.py`,
      `app/schemas/remitos_reportes.py`, y el `app/routers/remitos.py`
      viejo (ya reemplazado en 4.4).
- [x] 6.2 Quitar el registro de `remitos_reportes` (y cualquier otro
      import huérfano) de `app/main.py`.
- [x] 6.3 Eliminar `tests/unit/test_remitos_clientes.py`,
      `tests/unit/test_remitos_estado.py`,
      `tests/unit/test_remitos_reportes.py` (protegían el código
      retirado).
- [x] 6.4 Grep de `Remitos`/`RemitoDetalles`/`remitos_service` en todo
      `app/` para confirmar que no queda ninguna referencia colgante.

## 7. Migración de datos (legacy → nuevo modelo)

- [x] 7.1 Escribir `scripts/migrate_remitos_to_pedidos_remitos.sql`
      (SQL puro, sin puerto a Python — ver design.md Decisión 7):
      `TRUNCATE ... RESTART IDENTITY CASCADE` sobre
      `pedidos_pedido_detalle`/`pedidos_pedido`/
      `remitos_remito_detalle`/`remitos_remito` al inicio; tablas temp
      de mapeo `legacy_id → id_nuevo` vía
      `nextval(pg_get_serial_sequence(...))`, mismo patrón que
      `scripts/migrate_ctacteprov_to_compras.sql`.
- [x] 7.2 Cada fila `costos_remitos` genera un `Pedido` +
      `PedidoDetalle` por cada `costos_remitodetalles` asociada
      (`cantidad_pedida = cantidad`, `cantidad_entregada =
      COALESCE(entregado, 0)`), con `Pedido.estado` derivado del
      `estado` legacy según la tabla de mapeo de design.md Decisión 7
      (`creado→PENDIENTE`, ..., `facturado→ENTREGADO`).
- [x] 7.3 Para las filas legacy con `fecha_despacho IS NOT NULL`
      (estado `listo_entregar`/`en_entrega`/`facturado`) y al menos
      una línea con `entregado > 0`: generar además un `Remito`
      (`tipo=VENTA`, `pedido_id` al pedido recién creado,
      `cliente_id` del pedido) con una línea por cada
      `costos_remitodetalles.entregado > 0`, y sus timestamps
      (`fecha_despacho`/`fecha_recibido`) copiados del legacy — ver
      mapeo exacto en design.md Decisión 7. Filas que llegan a ese
      estado sin ninguna línea entregada no generan remito; quedan
      listadas en la verificación de salida (8.5).
- [x] 7.4 Correr el script (dentro de `BEGIN;`/`ROLLBACK;` primero)
      contra la base de datos de test local y comparar manualmente
      algunas filas conocidas antes de considerarlo listo para
      producción.
- [x] 7.5 Bloque de `SELECT`s de verificación al final del script:
      conteo de pedidos/remitos migrados, filas con `estado` legacy
      desconocido (fuera de las 6 etiquetas esperadas), y filas que
      alcanzaron `listo_entregar`+ sin ninguna línea `entregado > 0`
      (candidatas a revisión manual, ver 8.3).
- [x] 7.6 No correr este script contra producción como parte de este
      change salvo pedido explícito — coordinarlo con el usuario (ver
      9.3).

## 8. Reportes de pedidos (`pedidos_reportes`)

- [x] 8.1 `app/schemas/pedido_reportes.py`: `PedidosPendientesPorDia`
      (`total_pedidos`, `total_pendientes`, `total_en_preparacion`,
      `total_listo_para_entrega`, `total_entregados`,
      `total_cancelados`, `pedidos: list[PedidoRead]`),
      `ProductoPendienteItem`, `ResponsableProductosPendientes`,
      `ProductosPendientesPorDia` — ver design.md Decisión 8.
- [x] 8.2 `app/routers/pedidos_reportes.py`: puerto de
      `remitos_reportes.py` (ver git history) a `Pedido`/
      `PedidoDetalle` — `GET /pedidos-reportes/pendientes-entrega`,
      `GET /pedidos-reportes/pendientes-por-dia`,
      `GET /pedidos-reportes/productos-pendientes-por-dia`. Registrar
      en `app/main.py`.
- [x] 8.3 Tests: `tests/unit/test_pedidos_reportes.py` cubriendo los
      escenarios de "Reportes de pedidos pendientes" en
      `specs/pedidos/spec.md`.

## 9. Verificación

- [x] 9.1 `pytest tests/unit -q` verde completo.
- [x] 9.2 `openspec validate pedidos-y-remitos --type change --strict
      --json` pasa.
- [x] 9.3 Confirmado con el usuario: `panacea-mayorista-backend` (u
      otro consumidor externo de `/costos/remitos*`) todavía **no**
      está listo para el contrato nuevo — la migración SQL (0019 +
      `scripts/migrate_remitos_to_pedidos_remitos.sql`) **no** se
      aplica contra producción en este change. El código queda listo;
      aplicar la migración es un paso posterior y manual, a coordinar
      cuando el consumidor externo esté listo.
- [x] 9.4 Confirmado con el usuario: sí hace falta un equivalente a
      `remitos_reportes.py` — ver grupo 8 (`pedidos_reportes`).
- [x] 9.5 Confirmado con el usuario: las tablas legacy
      `costos_remitos`/`costos_remitodetalles` NO se dropean en este
      change (quedan como archivo histórico read-only — ver design.md
      Migration Plan paso 7 y Decisión 6). Sin fecha decidida para
      dropearlas; queda anotado para cuando se retome este branch.
