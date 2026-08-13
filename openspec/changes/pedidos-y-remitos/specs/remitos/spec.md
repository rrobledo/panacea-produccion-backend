## ADDED Requirements

### Requirement: Remito tiene un tipo VENTA o TRANSFERENCIA con campos condicionales
El sistema SHALL modelar `Remito` con un campo `tipo` obligatorio,
`VENTA` o `TRANSFERENCIA`. Un remito `VENTA` SHALL requerir
`cliente_id` y SHALL permitir `pedido_id` opcional (nulo si es una
venta directa sin pedido previo); `origen_sucursal_id` y
`destino_sucursal_id` SHALL ser nulos en un remito `VENTA`. Un remito
`TRANSFERENCIA` SHALL requerir `origen_sucursal_id` y
`destino_sucursal_id` (distintos entre sí), y SHALL tener
`cliente_id`/`pedido_id` nulos. El sistema SHALL rechazar con 400
cualquier combinación que no cumpla estas reglas (esta validación vive
en el schema Pydantic de request, y este repo convierte todo error de
validación de payload a 400 — ver
`app/main.py::validation_exception_handler` — no 422 genérico de
FastAPI).

#### Scenario: Crear remito de venta sin pedido
- **WHEN** un caller envía `POST /remitos` con `tipo=VENTA`,
  `cliente_id` y detalle, sin `pedido_id`
- **THEN** la respuesta es 201 con el remito creado y `pedido_id=null`

#### Scenario: Crear remito de venta con pedido
- **WHEN** el sistema genera un remito `VENTA` a partir de la
  transición de un pedido (ver capability `pedidos`)
- **THEN** el remito queda con `pedido_id` apuntando a ese pedido y
  `cliente_id` igual al del pedido

#### Scenario: Crear remito de transferencia entre sucursales
- **WHEN** un caller envía `POST /remitos` con `tipo=TRANSFERENCIA`,
  `origen_sucursal_id` y `destino_sucursal_id` distintos, y detalle,
  sin `cliente_id` ni `pedido_id`
- **THEN** la respuesta es 201 con el remito creado

#### Scenario: Transferencia con origen igual a destino es rechazada
- **WHEN** un caller envía `POST /remitos` con `tipo=TRANSFERENCIA` y
  `origen_sucursal_id == destino_sucursal_id`
- **THEN** la respuesta es 400 y no se crea el remito

#### Scenario: Venta con origen/destino de sucursal es rechazada
- **WHEN** un caller envía `POST /remitos` con `tipo=VENTA` y además
  `origen_sucursal_id` seteado
- **THEN** la respuesta es 400 y no se crea el remito

#### Scenario: Transferencia con cliente_id es rechazada
- **WHEN** un caller envía `POST /remitos` con `tipo=TRANSFERENCIA` y
  además `cliente_id` seteado
- **THEN** la respuesta es 400 y no se crea el remito

### Requirement: El remito creado manualmente nace en LISTO
El sistema SHALL crear todo `Remito` creado vía `POST /remitos`
directamente en estado `LISTO`, seteando `fecha_listo` en el momento
de creación. No existe un paso previo `PENDIENTE`/`EN_PREPARACION`.

#### Scenario: Un remito recién creado queda en LISTO
- **WHEN** un caller crea un remito vía `POST /remitos`
- **THEN** la respuesta es 201 con `estado="LISTO"` y `fecha_listo`
  seteada

### Requirement: El remito generado desde un Pedido nace en RECIBIDO
El sistema SHALL crear todo `Remito` generado automáticamente al
transicionar un `Pedido` a `LISTO_PARA_ENTREGA`/`ENTREGADO` (ver
capability `pedidos`) directamente en estado `RECIBIDO`, seteando
`fecha_listo`, `fecha_despacho` y `fecha_recibido` en el momento de
creación — el pedido ya documenta la entrega, el remito no necesita
su propio seguimiento de despacho/recepción.

#### Scenario: Remito generado desde un pedido queda RECIBIDO
- **WHEN** el sistema genera un remito a partir de la transición de un
  pedido a `LISTO_PARA_ENTREGA`
- **THEN** el remito queda con `estado="RECIBIDO"` desde su creación

### Requirement: Transiciones de estado del remito
El sistema SHALL exponer `PATCH /remitos/{id}/estado` avanzando el
remito únicamente al siguiente estado válido en la secuencia
`LISTO → EN_TRANSITO → RECIBIDO`, seteando el timestamp
correspondiente a ese paso. Transiciones que salteen un paso o
retrocedan SHALL ser rechazadas con 422. Esta regla SHALL aplicar
igual para remitos `VENTA` y `TRANSFERENCIA`.

#### Scenario: Transición válida de un paso
- **WHEN** un remito en `LISTO` recibe `PATCH .../estado` con
  `{"nuevo_estado": "EN_TRANSITO"}`
- **THEN** la respuesta es 200 y el remito queda en `EN_TRANSITO`

#### Scenario: Transición salteando un paso es rechazada
- **WHEN** un remito en `LISTO` recibe una transición a `RECIBIDO`
- **THEN** la respuesta es 422 y el estado no cambia

#### Scenario: Transición retrocediendo es rechazada
- **WHEN** un remito en `EN_TRANSITO` recibe una transición a `LISTO`
- **THEN** la respuesta es 422 y el estado no cambia

### Requirement: Edición y borrado de remito restringidos a LISTO
El sistema SHALL rechazar con 422 `PUT /remitos/{id}` y `DELETE
/remitos/{id}` cuando el remito no está en estado `LISTO` (es decir,
ya despachado o recibido), dejando el remito (y sus líneas de detalle)
sin modificar.

#### Scenario: Editar un remito en LISTO
- **WHEN** un remito en `LISTO` recibe un `PUT` válido
- **THEN** la respuesta es 200 y el remito se actualiza

#### Scenario: Borrar un remito no LISTO es rechazado
- **WHEN** un remito en `EN_TRANSITO` recibe `DELETE /remitos/{id}`
- **THEN** la respuesta es 422 y el remito sigue existiendo

### Requirement: Listado filtrable de remitos
El sistema SHALL permitir listar remitos vía `GET /remitos` filtrando
por `tipo`, `cliente_id`, `pedido_id`, `origen_sucursal_id`,
`destino_sucursal_id`, `estado`, y rango de fecha (`fecha_desde`/
`fecha_hasta` sobre `fecha_carga`).

#### Scenario: Filtrar remitos de transferencia hacia la fábrica
- **WHEN** un caller envía `GET /remitos?tipo=TRANSFERENCIA&destino_sucursal_id=<id_fabrica>`
- **THEN** la respuesta incluye únicamente remitos `TRANSFERENCIA` con
  ese `destino_sucursal_id`

#### Scenario: Filtrar remitos generados por un pedido
- **WHEN** un caller envía `GET /remitos?pedido_id=<id>`
- **THEN** la respuesta incluye todos los remitos (uno o más) generados
  a partir de ese pedido
