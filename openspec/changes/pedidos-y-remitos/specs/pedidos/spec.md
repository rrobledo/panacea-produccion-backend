## ADDED Requirements

### Requirement: Alta de pedido con detalle
El sistema SHALL permitir crear un `Pedido` vía `POST /pedidos` con
`cliente_id`, `vendedor`, `fecha_entrega`, `observaciones` opcionales,
y una lista de `PedidoDetalle` (`producto_id`, `cantidad_pedida`).
Cada `PedidoDetalle` SHALL inicializarse con `cantidad_entregada=0`. El
pedido creado SHALL quedar en estado `PENDIENTE` con `fecha_carga`
seteada al momento de creación.

#### Scenario: Crear un pedido con dos líneas
- **WHEN** un caller envía `POST /pedidos` con `cliente_id`,
  `vendedor`, `fecha_entrega` y dos líneas de detalle con
  `cantidad_pedida > 0`
- **THEN** la respuesta es 201, el pedido queda en estado `PENDIENTE`
  y cada línea tiene `cantidad_entregada=0`

### Requirement: Transiciones de estado del pedido
El sistema SHALL exponer `PATCH /pedidos/{id}/estado` avanzando el
pedido únicamente al siguiente estado válido en la secuencia
`PENDIENTE → EN_PREPARACION → PREPARADO → LISTO_PARA_ENTREGA →
ENTREGADO`, o a `CANCELADO` desde cualquier estado anterior a
`ENTREGADO`. Transiciones que salteen un paso, retrocedan (salvo el
caso de entrega parcial adicional descripto en el requirement
siguiente) o partan de `ENTREGADO`/`CANCELADO` SHALL ser rechazadas
con 422.

#### Scenario: Transición válida de un paso
- **WHEN** un pedido en `PENDIENTE` recibe `PATCH .../estado` con
  `{"nuevo_estado": "EN_PREPARACION"}`
- **THEN** la respuesta es 200 y el pedido queda en `EN_PREPARACION`

#### Scenario: Transición salteando un paso es rechazada
- **WHEN** un pedido en `PENDIENTE` recibe una transición a
  `LISTO_PARA_ENTREGA`
- **THEN** la respuesta es 422 y el estado no cambia

#### Scenario: Transición desde ENTREGADO es rechazada
- **WHEN** un pedido en `ENTREGADO` recibe cualquier transición
- **THEN** la respuesta es 422 y el estado no cambia

### Requirement: Historial de fechas por estado
El sistema SHALL registrar, para cada estado alcanzado por un
`Pedido` (`EN_PREPARACION`, `PREPARADO`, `LISTO_PARA_ENTREGA`,
`ENTREGADO`, `CANCELADO`), la fecha en que se produjo esa transición
(`fecha_en_preparacion`, `fecha_preparado`,
`fecha_listo_para_entrega`, `fecha_entregado`, `fecha_cancelado`
respectivamente), de forma análoga al historial de fechas de
`Remito`. `PENDIENTE` no tiene fecha propia — usa `fecha_carga`, ya
existente. Estas fechas son puramente informativas: `Pedido.estado`
sigue siendo un campo propio, no se deriva de ellas (a diferencia de
`Remito.estado`), porque `CANCELADO` es una transición lateral que no
encaja en una precedencia lineal de timestamps.

#### Scenario: Cada transición setea su fecha
- **WHEN** un pedido en `PENDIENTE` recibe `PATCH .../estado` con
  `{"nuevo_estado": "EN_PREPARACION"}`
- **THEN** la respuesta es 200 y el pedido queda con
  `fecha_en_preparacion` seteada al momento de la transición

#### Scenario: Cancelar setea fecha_cancelado
- **WHEN** un pedido recibe `PATCH .../estado` con
  `{"nuevo_estado": "CANCELADO"}`
- **THEN** la respuesta es 200 y el pedido queda con `fecha_cancelado`
  seteada

### Requirement: Registro de entrega parcial por línea
El sistema SHALL permitir actualizar `cantidad_entregada` de una o más
líneas de un pedido no `CANCELADO` vía `PATCH
/pedidos/{id}/entrega`, aceptando por línea una `cantidad_entregada`
que SHALL ser mayor o igual a la ya registrada y menor o igual a
`cantidad_pedida`. Esto SHALL poder hacerse en cualquier estado previo
a `ENTREGADO`, incluyendo después de que el pedido ya generó un
remito parcial.

#### Scenario: Registrar entrega parcial de una línea
- **WHEN** una línea con `cantidad_pedida=10` y `cantidad_entregada=0`
  recibe `PATCH .../entrega` con `cantidad_entregada=6`
- **THEN** la respuesta es 200 y la línea queda con
  `cantidad_entregada=6`

#### Scenario: Entrega mayor a lo pedido es rechazada
- **WHEN** una línea con `cantidad_pedida=10` y `cantidad_entregada=6`
  recibe `PATCH .../entrega` con `cantidad_entregada=11`
- **THEN** la respuesta es 422 y la línea no se modifica

#### Scenario: Entrega menor a lo ya entregado es rechazada
- **WHEN** una línea con `cantidad_entregada=6` recibe `PATCH
  .../entrega` con `cantidad_entregada=3`
- **THEN** la respuesta es 422 y la línea no se modifica

### Requirement: Generación automática de remito al completar la entrega
El sistema SHALL crear automáticamente un `Remito`, en la misma
transacción, cuando `PATCH /pedidos/{id}/estado` mueve un pedido a
`LISTO_PARA_ENTREGA` o `ENTREGADO`. El remito generado SHALL ser de
tipo `VENTA` con `pedido_id` igual al del pedido, `cliente_id` igual
al del pedido, y una línea de `RemitoDetalle` por cada
`PedidoDetalle` cuya `cantidad_entregada` creció desde el último
remito generado para ese pedido (o desde la creación del pedido, si
es el primero), con `cantidad` igual a ese incremento. El remito
generado SHALL crearse directamente en estado `RECIBIDO` (sin pasar
por `LISTO`/`EN_TRANSITO`): el pedido llegando a
`LISTO_PARA_ENTREGA`/`ENTREGADO` ya documenta la entrega, así que el
remito no requiere su propio seguimiento de despacho/recepción. Si
ningún
`PedidoDetalle` tiene incremento de `cantidad_entregada` en el
momento de la transición Y el pedido nunca generó un remito
anteriormente, la transición SHALL ser rechazada con 422 (no tiene
sentido generar el primer remito vacío). Si el pedido ya generó al
menos un remito antes y no hay incremento nuevo, la transición SHALL
completarse igual (200) sin generar un remito adicional — típicamente
porque todo lo pedido ya se entregó de una sola vez en el paso
anterior, y este paso es solo administrativo.

#### Scenario: Transición genera el remito con lo entregado
- **WHEN** un pedido con una línea `cantidad_pedida=10,
  cantidad_entregada=6` (sin remitos previos) recibe `PATCH
  .../estado` a `LISTO_PARA_ENTREGA`
- **THEN** la respuesta es 200, el pedido pasa a `LISTO_PARA_ENTREGA`,
  y se crea un `Remito` tipo `VENTA` en estado `RECIBIDO` con
  `pedido_id` del pedido y una línea con `cantidad=6`

#### Scenario: Segunda tanda de entrega genera un segundo remito
- **WHEN** un pedido que ya generó un remito por `cantidad_entregada=6`
  recibe una entrega parcial adicional que sube `cantidad_entregada` a
  10, y vuelve a transicionar a `ENTREGADO`
- **THEN** se crea un segundo `Remito` con `pedido_id` del mismo
  pedido y una línea con `cantidad=4` (el incremento, no el
  acumulado)

#### Scenario: Transición sin entrega nueva pero con remito previo no genera uno nuevo
- **WHEN** un pedido con `cantidad_pedida=10` se entrega por completo
  (`cantidad_entregada=10`) y transiciona a `LISTO_PARA_ENTREGA`
  (generando un remito con `cantidad=10`), y luego recibe `PATCH
  .../estado` a `ENTREGADO` sin ninguna entrega adicional
- **THEN** la respuesta es 200, el pedido pasa a `ENTREGADO`, y sigue
  existiendo un único `Remito` para ese pedido (no se genera un
  segundo remito vacío)

#### Scenario: Transición sin ninguna entrega registrada es rechazada
- **WHEN** un pedido que nunca registró ninguna entrega
  (`cantidad_entregada=0` en todas sus líneas, sin remitos previos)
  recibe `PATCH .../estado` a `LISTO_PARA_ENTREGA`
- **THEN** la respuesta es 422 y no se crea ningún remito

#### Scenario: Falla al generar el remito revierte la transición
- **WHEN** la creación del `Remito` falla dentro de la transacción de
  `PATCH .../estado`
- **THEN** la respuesta es un error, el pedido permanece en su estado
  anterior y no queda ningún `Remito` parcial creado

### Requirement: Edición y borrado de pedido restringidos a PENDIENTE
El sistema SHALL rechazar con 422 `PUT /pedidos/{id}` y `DELETE
/pedidos/{id}` cuando el pedido no está en estado `PENDIENTE`, dejando
el pedido sin modificar.

#### Scenario: Editar un pedido PENDIENTE
- **WHEN** un pedido en `PENDIENTE` recibe un `PUT` válido
- **THEN** la respuesta es 200 y el pedido se actualiza

#### Scenario: Editar un pedido en EN_PREPARACION es rechazado
- **WHEN** un pedido en `EN_PREPARACION` recibe `PUT /pedidos/{id}`
- **THEN** la respuesta es 422 y el pedido no se modifica

### Requirement: Reportes de pedidos pendientes
El sistema SHALL exponer `GET /pedidos-reportes/pendientes-entrega`
(todos los pedidos ordenados por `fecha_entrega`),
`GET /pedidos-reportes/pendientes-por-dia` (pedidos agrupados por día
de `fecha_entrega`, con conteo por bucket de estado:
`total_pendientes`, `total_en_preparacion` — que agrupa
`EN_PREPARACION` y `PREPARADO` —, `total_listo_para_entrega`,
`total_entregados`, `total_cancelados`) y
`GET /pedidos-reportes/productos-pendientes-por-dia` (suma de
`cantidad_pedida - cantidad_entregada` por producto y responsable,
agrupada por día de `fecha_entrega`, para pedidos cuyo estado no sea
`ENTREGADO` ni `CANCELADO`).

#### Scenario: Pendientes por día agrupa y cuenta por estado
- **WHEN** existen dos pedidos con la misma `fecha_entrega` (un día),
  uno en `PENDIENTE` y otro en `PREPARADO`, y un tercer pedido en otro
  día en `EN_PREPARACION`
- **THEN** `GET /pedidos-reportes/pendientes-por-dia` devuelve dos
  entradas: la del primer día con `total_pedidos=2`,
  `total_pendientes=1`, `total_en_preparacion=1`; la del segundo día
  con `total_pedidos=1`, `total_en_preparacion=1`

#### Scenario: Productos pendientes por día excluye pedidos cerrados
- **WHEN** un pedido `ENTREGADO` y otro `CANCELADO` tienen líneas con
  `cantidad_pedida > cantidad_entregada`, y un tercer pedido
  `PENDIENTE` tiene una línea con `cantidad_pedida=10,
  cantidad_entregada=4`
- **THEN** `GET /pedidos-reportes/productos-pendientes-por-dia` solo
  incluye la línea pendiente del tercer pedido, con `cantidad=6`
