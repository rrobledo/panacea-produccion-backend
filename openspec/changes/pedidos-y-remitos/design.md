## Context

`app/models/remitos.py` hoy modela un único documento (`Remitos` +
`RemitoDetalles`, tabla `costos_remitos`/`costos_remitodetalles`) que
funciona a la vez como pedido de cliente y comprobante de entrega: un
estado lineal derivado de 5 timestamps (`fecha_preparacion`,
`fecha_listo`, `fecha_despacho`, `fecha_recibido`, `fecha_facturacion`)
y una columna `entregado` por línea de detalle. El router/servicio
actual documenta explícitamente que replica el contrato de
`panacea-mayorista-backend` (mismos nombres de estado, mismas reglas de
transición) — es un consumidor externo real, no solo un detalle
interno.

No existe ningún concepto de sucursal en el backend: ni tabla, ni
referencia en otros modelos (`app/models/*.py` no tiene nada con
"sucursal"). Los traslados internos de mercadería (sucursal↔sucursal,
sucursal→fábrica) no tienen dónde vivir hoy.

Decisión ya tomada con el usuario (no abierta a discusión en este
design): se redefine `remito` como capability nueva — **BREAKING**,
sin mantener compatibilidad con el contrato actual de mayorista — y se
introduce un catálogo `Sucursal` nuevo en vez de campos de texto libre.

## Goals / Non-Goals

**Goals:**
- Separar la intención de compra del cliente (`Pedido`) del comprobante
  físico de traslado/entrega (`Remito`).
- Permitir que un `Pedido` se despache en más de una tanda, trackeando
  `cantidad_entregada` por línea de forma independiente de
  `cantidad_pedida`.
- Generar automáticamente un `Remito` de venta cuando un `Pedido`
  alcanza `LISTO_PARA_ENTREGA`/`ENTREGADO`.
- Permitir crear un `Remito` de tipo `TRANSFERENCIA` sin cliente ni
  pedido, entre dos `Sucursal` (o sucursal→fábrica).
- Dar de baja limpiamente el modelo `Remitos` actual y todo lo que
  depende de él.

**Non-Goals:**
- No se define ni implementa nada del lado de
  `panacea-mayorista-backend` — ese repo queda fuera del alcance, se
  asume que se actualiza por separado contra el contrato nuevo.
- No se modela stock/inventario (cantidades disponibles por sucursal);
  el remito de transferencia registra el movimiento de mercadería
  entre sucursales pero no valida contra un saldo de stock — eso
  requeriría un modelo de inventario que no existe hoy.

## Decisions

### 1. Dos entidades, no una jerarquía con subtipos

`Pedido`/`PedidoDetalle` y `Remito`/`RemitoDetalle` son tablas
independientes, unidas por `Remito.pedido_id` (FK nullable). Se
descartó modelar `Remito` como una subclase/extensión de `Pedido`
(single-table inheritance) porque un remito de tipo `TRANSFERENCIA` no
tiene cliente, vendedor ni ninguno de los campos propios de un pedido
— forzar esa forma hubiera dejado la mitad de las columnas NULL para
todos los remitos internos. Dos tablas separadas con una FK opcional
modelan directamente "puede tener o no una nota de pedido".

### 2. `Remito.tipo` (VENTA / TRANSFERENCIA) en vez de dos tablas de remito

Se evaluó tener `RemitoVenta` y `RemitoTransferencia` como tablas
separadas. Se descartó: comparten casi todo el ciclo de vida (mismo
flujo de estados, mismo patrón de detalle con producto/cantidad, mismo
patrón de adjuntos si se necesitan a futuro) y separarlas duplicaría
routers/servicios/schemas casi al 100%. Una sola tabla `Remito` con
`tipo` y columnas condicionalmente obligatorias
(`cliente_id`/`pedido_id` para `VENTA`; `origen_sucursal_id`/
`destino_sucursal_id` para `TRANSFERENCIA`) valida la combinación
correcta a nivel de servicio (Pydantic `model_validator`), mismo
patrón que ya usa este repo en otros lados para condicionales de
payload (p.ej. `CompraDetalle.tipo` en el change de cuenta corriente
de proveedores).

### 3. Generación de remito: automática, en la misma transacción que la transición de estado del pedido

Cuando `PATCH /pedidos/{id}/estado` mueve un `Pedido` a
`LISTO_PARA_ENTREGA` (la nota queda lista para el flete/reparto) o
directamente a `ENTREGADO` (entrega en mano, sin paso intermedio), el
servicio de pedidos crea el `Remito` tipo `VENTA` dentro de la misma
transacción de la transición, con:
- `pedido_id` = el pedido de origen
- `cliente_id` = `Pedido.cliente_id`
- `RemitoDetalle` por cada `PedidoDetalle` con `cantidad_entregada > 0`
  en ese momento, copiando esa cantidad como `cantidad` fija del
  remito (el remito es una foto del despacho, no una referencia viva
  al pedido)

Se evaluó generar el remito en un paso manual explícito
(`POST /pedidos/{id}/generar-remito`) separado de la transición de
estado. Se descartó porque el pedido del usuario es explícito ("cuando
la nota de pedido pasa a entregada o lista para entrega **se
transforma** en remito") — la generación es una consecuencia directa
del cambio de estado, no una acción aparte que alguien pueda olvidar
disparar.

**Un pedido puede generar más de un remito** si se entrega en varias
tandas: tanto `LISTO_PARA_ENTREGA` como `ENTREGADO` son transiciones
"generadoras" (ver Decisión 3.1 sobre qué pasa cuando no hay nada
nuevo que remitir en alguna de ellas), así que un pedido que se
entrega de a poco genera un remito en cada paso que tiene algo nuevo
entregado. Esto no requiere que `Pedido` retroceda de estado en ningún
momento — las dos transiciones (`PREPARADO→LISTO_PARA_ENTREGA` y
`LISTO_PARA_ENTREGA→ENTREGADO`) ya son parte de la secuencia lineal
normal; lo único especial es que ambas, no solo la última, pueden
disparar generación de remito.

#### 3.1 Transición generadora sin nada nuevo que remitir: no es un error si ya hubo un remito antes

La primera versión de esta regla rechazaba con 422 *cualquier*
transición a `LISTO_PARA_ENTREGA`/`ENTREGADO` sin incremento de
`cantidad_entregada`. Escrito así, un pedido entregado 100% de una
sola vez quedaba trabado para siempre en `LISTO_PARA_ENTREGA`: ese
paso ya consume todo el incremento, así que no queda nada nuevo para
`ENTREGADO`, y la transición que debería ser el cierre administrativo
del pedido fallaba con 422. Corregido durante la implementación (ver
`tests/unit/test_pedidos.py::test_transicion_desde_entregado_es_rechazada`,
que reveló el problema): el 422 aplica **solo** cuando el pedido nunca
generó ningún remito todavía (no tiene sentido el primer remito
vacío). Si ya existe al menos un remito para ese pedido y la
transición actual no tiene ningún incremento, la transición igual se
completa (200) sin crear un remito adicional — típicamente porque todo
se entregó de una sola vez en el paso anterior y este paso es solo
administrativo. Ver el Requirement actualizado y sus escenarios en
`specs/pedidos/spec.md`.

### 4. Estado de `Remito`: flujo de logística propio, desacoplado del estado de `Pedido`

`Remito` tiene su propio estado lineal
(`PENDIENTE → EN_PREPARACION → LISTO → EN_TRANSITO → RECIBIDO`),
independiente del de `Pedido`. Es el mismo patrón que ya usaba
`Remitos.estado` (secuencia de timestamps), pero renombrado para no
confundirse con los estados de `Pedido` y sin el paso `facturado`
final (facturación no es parte de este change — no hay evidencia en
el código actual de que algo dependa de `fecha_facturacion` fuera del
propio cálculo de `estado`; si hace falta se agrega en un change
aparte). Un remito `TRANSFERENCIA` recorre el mismo flujo que uno
`VENTA` — preparar/despachar/recibir mercadería es la misma mecánica
tenga o no cliente/pedido detrás.

Edición y borrado de `Remito` se restringen a estado `PENDIENTE`,
mismo patrón que ya existía en el código actual (`_ensure_creado`) —
sin cambios de fondo en esa regla, solo el rename de estados.

### 5. `Sucursal`: catálogo mínimo, sin jerarquía ni domicilio

`Sucursal` es `id`, `nombre`, `tipo` (`SUCURSAL`/`FABRICA`), `activa`
(bool, default `true`). No se modelan domicilio, zona ni relación con
`Clientes` — no hay ningún requerimiento del usuario que lo pida, y
agregar esos campos ahora sería especular sobre necesidades futuras de
reporting. Si aparece esa necesidad, es un campo más sobre una tabla
que ya existe, no un rediseño.

### 6. Borrado limpio del código legacy; las tablas legacy NO se dropean

Se eliminan por completo `app/models/remitos.py`,
`app/schemas/remitos.py`, `app/services/remitos_service.py`,
`app/routers/remitos.py`, `app/routers/remitos_reportes.py`,
`app/schemas/remitos_reportes.py` y su registro en `app/main.py`. A
diferencia de ese código, las tablas `costos_remitos`/
`costos_remitodetalles` **no se dropean** en la migración de schema
(grupo 1 de `tasks.md`) — quedan como archivo histórico read-only,
mismo patrón exacto que `redesign-cuenta-corriente-proveedor` dejó
`costos_cuentacorrienteproveedor*` sin dropear: son la fuente que lee
el script de backfill de la Decisión 7. No queda un período de doble
escritura ni un flag de feature en el código de la app — mismo
criterio que el cutover de `/ctacteprov*` (retiro directo del código
una vez que el consumidor externo puede migrar), pero el retiro de las
tablas en sí queda fuera de alcance de este change (se dropean a mano,
más adelante, una vez confirmado que el backfill corrió bien contra
producción).

### 7. Script de backfill: puramente SQL, mismo patrón que `migrate_ctacteprov_to_compras.sql`

Se agrega `scripts/migrate_remitos_to_pedidos_remitos.sql`, un script
SQL puro (sin contraparte Python — a diferencia del backfill de
`redesign-cuenta-corriente-proveedor`, acá no se pidió puerto a
Python) que migra cada fila de `costos_remitos`/`costos_remitodetalles`
a `Pedido`/`PedidoDetalle` y, cuando corresponde, a
`Remito`/`RemitoDetalle`. Mismo patrón que el script de referencia:
`TRUNCATE ... RESTART IDENTITY CASCADE` sobre las tablas destino al
inicio (re-corrible), tablas temp de mapeo id-legacy→id-nuevo vía
`nextval(pg_get_serial_sequence(...))`, y un bloque de `SELECT`s de
verificación al final en vez de un resumen impreso.

Reglas de mapeo (una fila legacy → siempre un `Pedido`, y
condicionalmente un `Remito`):

- **Cada fila `costos_remitos` genera exactamente un `Pedido`**,
  copiando `cliente_id`, `vendedor`, `observaciones`, `fecha_carga`,
  `fecha_entrega` verbatim, y cada `costos_remitodetalles` asociada
  genera un `PedidoDetalle` con `cantidad_pedida = cantidad` y
  `cantidad_entregada = COALESCE(entregado, 0)`.
- **`Pedido.estado`** se deriva del `estado` legacy (la misma
  precedencia de timestamps que ya calculaba `Remitos.estado`):
  `creado→PENDIENTE`, `en_produccion→EN_PREPARACION`,
  `preparando→PREPARADO`, `listo_entregar→LISTO_PARA_ENTREGA`,
  `en_entrega→ENTREGADO`, `facturado→ENTREGADO` (no hay estado de
  pedido para "facturado" — cae en `ENTREGADO`, con una nota en
  `observaciones`).
- **Se genera un `Remito` (`tipo=VENTA`, `pedido_id` al pedido recién
  creado, `cliente_id` del mismo pedido) solo para las filas cuyo
  `estado` legacy sea `listo_entregar`, `en_entrega` o `facturado`**
  (i.e. `fecha_despacho IS NOT NULL`) — el mismo umbral que
  `LISTO_PARA_ENTREGA`/`ENTREGADO` dispara la generación automática en
  el sistema nuevo (Decisión 3). Sus líneas son una por cada
  `costos_remitodetalles` con `entregado > 0`, `cantidad = entregado`.
  Si una fila alcanzó ese umbral pero ninguna línea tiene `entregado >
  0`, no se genera remito para ella (mismo criterio que la Requirement
  "no tiene sentido generar un remito vacío" de `specs/pedidos/spec.md`)
  y queda listada en la verificación de salida para revisión manual.
- **Timestamps del `Remito` generado**: como el remito nuevo solo
  existe a partir del momento en que el pedido legacy llegó a
  "despachado", su propio ciclo de vida (`PENDIENTE→EN_PREPARACION→
  LISTO→EN_TRANSITO→RECIBIDO`) arranca directamente en
  `EN_TRANSITO` — `fecha_despacho` del remito nuevo = `fecha_despacho`
  legacy, y si el legacy llegó a `en_entrega`/`facturado`,
  `fecha_recibido` del remito nuevo = `fecha_recibido` legacy
  (`RECIBIDO`). `fecha_preparacion`/`fecha_listo` del remito nuevo
  quedan `NULL`: esos pasos ya estaban representados por las
  transiciones `EN_PREPARACION`/`PREPARADO` del `Pedido`, no hay un
  timestamp legacy independiente para el propio ciclo del remito. Es
  una limitación aceptada de reconstruir dos flujos de estado
  separados a partir de uno solo — ver Risks.
- **No se migra `costos_remitos` a `Sucursal`/remitos `TRANSFERENCIA`**:
  el legacy no tiene ningún concepto de traslado interno, así que no
  hay nada que mapear a ese `tipo`; los remitos de transferencia solo
  se crean hacia adelante, vía la API nueva.

### 8. `app/routers/remitos_reportes.py` se reconstruye sobre `Pedido`, no sobre `Remito`

Pedido explícito del usuario durante la implementación (revierte el
Non-Goal original de este mismo design.md, que dejaba esto fuera de
alcance). El viejo `remitos_reportes.py` reportaba sobre
`Remitos.estado` — el flujo de 6 pasos (`creado → en_produccion →
preparando → listo_entregar → en_entrega → facturado`) que mezclaba
preparación/producción (ahora del lado de `Pedido`) con
despacho/entrega (ahora del lado de `Remito`). Sus tres endpoints
(`pendientes-entrega`, `pendientes-por-dia`,
`productos-pendientes-por-dia`) calculaban todos "cuánto falta
producir/entregar de cada pedido", nunca nada específico del
despacho físico (ningún campo tocaba `fecha_despacho`/`fecha_recibido`
más que para derivar el estado) — por eso el reporte se porta a
`Pedido`/`PedidoDetalle` (`app/routers/pedidos_reportes.py`,
`app/schemas/pedido_reportes.py`), no a `Remito`.

Mapeo de los tres endpoints:
- `GET /pedidos-reportes/pendientes-entrega`: mismo comportamiento
  literal que el original — devuelve todos los `Pedido` ordenados por
  `fecha_entrega`, sin filtrar por estado (el nombre es un poco
  engañoso pero así se comportaba `Remitos` también; se preserva la
  paridad exacta en vez de "corregirlo" sin que lo pida nadie).
- `GET /pedidos-reportes/pendientes-por-dia`: agrupa por
  `fecha_entrega` (día) y cuenta pedidos por bucket de estado. Como
  `Pedido` tiene 5 estados no-terminales/terminales (`PENDIENTE`,
  `EN_PREPARACION`, `PREPARADO`, `LISTO_PARA_ENTREGA`, `ENTREGADO`) más
  `CANCELADO`, en vez de los 6 del legacy, los buckets se redefinen
  1:1 con los estados de `Pedido` (`EN_PREPARACION`+`PREPARADO` siguen
  mergeados en `total_en_preparacion`, igual que el legacy mergeaba
  `en_produccion`+`preparando`) y se agrega `total_cancelados`. **Se
  elimina `total_en_camino`**: ese bucket legacy correspondía a
  `en_entrega` (mercadería ya despachada, aún no recibida) — ese
  concepto ahora vive exclusivamente en el estado de `Remito`
  (`EN_TRANSITO`), no en `Pedido`, así que no tiene equivalente en este
  reporte. Un reporte de remitos en tránsito, si hace falta, es un
  endpoint aparte sobre `Remito.estado`, fuera de alcance de este
  change.
- `GET /pedidos-reportes/productos-pendientes-por-dia`: mismo query
  agregado que el original (`cantidad - entregado` por
  producto/responsable/día), traducido a
  `cantidad_pedida - cantidad_entregada` sobre
  `pedidos_pedido_detalle`/`pedidos_pedido`, filtrando
  `estado NOT IN ('ENTREGADO', 'CANCELADO')` en vez del `fecha_facturacion
  IS NULL` legacy (equivalente: "todavía no cerrado").

**El puerto Python (`scripts/migrate_ctacteprov_to_compras.py`-style)
no aplica acá** — esto es un router de reportes de solo lectura, no un
script de backfill.

## Risks / Trade-offs

- [Romper a `panacea-mayorista-backend` sin coordinación] → Mitigación:
  este change no se aplica a producción hasta confirmar con el usuario
  que ese consumidor está listo para el contrato nuevo (mismo checkpoint
  que se usó para el cutover de `/ctacteprov*`). `tasks.md` deja esto
  como paso explícito antes de considerar el change completo.
- [El remito generado por el backfill no tiene timestamps propios de
  `EN_PREPARACION`/`LISTO` — arranca directo en `EN_TRANSITO`] →
  Mitigación: aceptado explícitamente (ver Decisión 7); esos pasos
  intermedios del legacy quedan representados del lado del `Pedido`
  migrado, no se inventan timestamps del lado del remito. Documentar
  esto si alguna vista de reportes asume que todo remito pasó por
  `EN_PREPARACION`/`LISTO`.
- [El script de backfill hace `TRUNCATE` de `pedidos_pedido`/
  `remitos_remito` antes de migrar, igual que el de referencia] →
  Mitigación: mismo trade-off aceptado que
  `migrate_ctacteprov_to_compras.sql` — solo correr contra una base
  donde esas tablas deban derivarse enteramente de `costos_remitos*`;
  documentado en el propio header del script.
- [Generación automática de remito falla a mitad de camino (pedido
  queda en `LISTO_PARA_ENTREGA` sin remito)] → Mitigación: la creación
  del remito y la transición de estado del pedido ocurren en la misma
  transacción de base de datos; si falla la generación del remito, la
  transición completa se revierte (el pedido no avanza de estado).
- [Remito de transferencia sin validación de stock puede registrar un
  traslado de mercadería que no existe en la sucursal de origen] →
  Mitigación explícita: fuera de alcance (ver Non-Goals); documentado
  para que no se asuma que este change garantiza consistencia de
  stock.

## Migration Plan

1. Migraciones SQL: crear `sucursales_sucursal`, `pedidos_pedido`,
   `pedidos_pedido_detalle`, `remitos_remito` (rediseñado),
   `remitos_remito_detalle`. **No** se toca `costos_remitos`/
   `costos_remitodetalles` (quedan intactas — ver Decisión 6). Mismo
   par `migrations/000N_*.sql` + `docker/init-db/0N_*.sql` que el
   resto del repo.
2. Agregar modelos/schemas/servicios/routers nuevos
   (`sucursales`, `pedidos`, `remitos`), registrar routers en
   `app/main.py`.
3. Eliminar el código legacy de `remitos` (modelo, schema, servicio,
   router, router de reportes) y su registro en `app/main.py`.
4. Correr `scripts/migrate_remitos_to_pedidos_remitos.sql` (dentro de
   `BEGIN;`/`ROLLBACK;` primero, como dry-run) contra la base real
   para poblar `pedidos_pedido*`/`remitos_remito*` con el historial de
   `costos_remitos*` — ver Decisión 7. Revisar el bloque de
   verificación al final antes de aplicar para real.
5. Tests unitarios nuevos para las tres capabilities; borrar tests que
   cubrían el `Remitos` legacy si quedan huérfanos.
6. Sin rollback automatizado para el schema nuevo: como cualquier otro
   change de este repo, revertir es revertir el commit/branch antes de
   aplicar la migración SQL en la base real. El script de backfill en
   sí es re-corrible (hace `TRUNCATE` de sus tablas destino al
   principio) y no toca las tablas legacy, así que puede repetirse sin
   riesgo para el historial de origen.
7. Las tablas legacy `costos_remitos`/`costos_remitodetalles` se
   dropean recién en un paso posterior y manual, una vez confirmado
   que el backfill corrió bien contra producción — fuera de alcance de
   este change (ver Open Questions).

## Open Questions

- ¿`panacea-mayorista-backend` (u otro consumidor externo de
  `/costos/remitos*`) está en condiciones de migrar al contrato nuevo
  en el mismo plazo que este backend? Bloqueante para aplicar la
  migración SQL contra producción (no para desarrollar el change).
- ¿Hace falta reponer algo equivalente a
  `app/routers/remitos_reportes.py` sobre el modelo nuevo, o los
  reportes actuales dejan de usarse? No estaba en el pedido original
  del usuario — a confirmar antes de dar por cerrado este change.
