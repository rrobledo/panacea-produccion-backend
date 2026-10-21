## ADDED Requirements

<!-- "responde 422" en los escenarios = la solicitud se rechaza: los errores de validación del payload salen 400 (handler de la app) y las reglas de negocio del servicio salen 422. -->

### Requirement: Envío único para pedidos y remitos
El sistema SHALL representar todo movimiento de mercadería (pedido de cliente, pedido de sucursal, remito directo a cliente y transferencia entre sucursales) con una única entidad de envío (`pedidos_pedido` + `pedidos_pedido_detalle`). El sistema MUST NOT persistir remitos en una tabla separada. Cada línea de detalle SHALL tener `cantidad_pedida` y `cantidad_entregada`, ambas enteras y >= 0. Una línea SHALL persistirse solo si al menos una de las dos es > 0.

#### Scenario: Pedido normal
- **WHEN** se crea un envío con `es_remito = false` y una línea con `cantidad_pedida = 10`
- **THEN** se persiste una línea con `cantidad_pedida = 10` y `cantidad_entregada = 0`, y el envío queda en `PENDIENTE`

#### Scenario: Línea vacía descartada
- **WHEN** se crea o edita un envío con una línea que tiene `cantidad_pedida = 0` y `cantidad_entregada = 0`
- **THEN** esa línea no se persiste

### Requirement: Remito directo como envío
El sistema SHALL permitir crear un envío con `es_remito = true` que representa un remito sin pedido previo. En un remito directo, todas las líneas MUST tener `cantidad_pedida = 0` y lo despachado en `cantidad_entregada`. El envío SHALL nacer en estado `LISTO_PARA_ENTREGA`, con `fecha_carga` y `fecha_listo_para_entrega` iguales al momento de creación.

#### Scenario: Alta de remito directo a cliente
- **WHEN** se crea un envío con `es_remito = true`, `tipo = CLIENTE`, `cliente_id = 5` y una línea con `cantidad_entregada = 8`
- **THEN** se persiste con `estado = LISTO_PARA_ENTREGA`, la línea con `cantidad_pedida = 0` y `cantidad_entregada = 8`

#### Scenario: Remito directo con cantidad pedida
- **WHEN** se crea un envío con `es_remito = true` y una línea con `cantidad_pedida = 3`
- **THEN** el sistema responde 422 y no persiste nada

#### Scenario: Remito directo sin líneas entregadas
- **WHEN** se crea un envío con `es_remito = true` y ninguna línea tiene `cantidad_entregada > 0`
- **THEN** el sistema responde 422

### Requirement: Tipo de destinatario y sucursales de origen y destino
El header SHALL usar `tipo` (`CLIENTE` | `SUCURSAL`) tanto para pedidos como para remitos. Con `tipo = CLIENTE`, `cliente_id` MUST estar informado y `sucursal_id`/`origen_sucursal_id` MUST ser null. Con `tipo = SUCURSAL`, `sucursal_id` (destino) MUST estar informado y `cliente_id` MUST ser null. `origen_sucursal_id` es opcional: si no se informa, el sistema SHALL asignar la única sucursal de tipo `FABRICA`. Origen y destino MUST ser distintos.

#### Scenario: Transferencia entre sucursales con origen explícito
- **WHEN** se crea un envío `es_remito = true`, `tipo = SUCURSAL`, `origen_sucursal_id = 2`, `sucursal_id = 3`
- **THEN** se persiste con origen 2 y destino 3

#### Scenario: Origen por defecto desde la fábrica
- **WHEN** se crea un envío `tipo = SUCURSAL`, `sucursal_id = 3`, sin `origen_sucursal_id`, y existe exactamente una sucursal `FABRICA` con id 1
- **THEN** se persiste con `origen_sucursal_id = 1`

#### Scenario: Sin fábrica unívoca
- **WHEN** se crea un envío `tipo = SUCURSAL` sin `origen_sucursal_id` y no hay exactamente una sucursal `FABRICA`
- **THEN** el sistema responde 422 indicando que no pudo determinar el origen

#### Scenario: Origen igual a destino
- **WHEN** se crea un envío `tipo = SUCURSAL` con `origen_sucursal_id = sucursal_id`
- **THEN** el sistema responde 422

### Requirement: Ítems agregados después de la carga original
Cada línea de detalle SHALL conservar su `fecha_creacion` original cuando se edita el envío (merge por `producto_id`). Una línea SHALL considerarse "agregada al pedido original" cuando su `fecha_creacion` es posterior a la `fecha_carga` del envío. La API SHALL exponer `fecha_creacion` por línea.

#### Scenario: Producto agregado en una edición
- **WHEN** a un envío creado el día 1 se le agrega el día 2 una línea nueva del producto 7
- **THEN** la línea del producto 7 tiene `fecha_creacion` del día 2 y las líneas existentes conservan la del día 1

### Requirement: Estados del envío
El envío SHALL usar la secuencia lineal `PENDIENTE → EN_PREPARACION → PREPARADO → LISTO_PARA_ENTREGA → ENTREGADO` y la transición lateral `CANCELADO` (desde cualquier estado excepto `ENTREGADO`/`CANCELADO`). Cada estado alcanzado SHALL registrar su fecha (`fecha_en_preparacion`, `fecha_preparado`, `fecha_listo_para_entrega`, `fecha_entregado`, `fecha_cancelado`). Un remito directo SHALL avanzar solo de `LISTO_PARA_ENTREGA` a `ENTREGADO`. Ninguna transición SHALL generar registros en otra entidad.

#### Scenario: Pedido llega a ENTREGADO
- **WHEN** un pedido en `LISTO_PARA_ENTREGA` pasa a `ENTREGADO`
- **THEN** el estado cambia, se setea `fecha_entregado` y no se crea ningún remito aparte

#### Scenario: Pedido sin entregas llega a LISTO_PARA_ENTREGA
- **WHEN** un pedido en `PREPARADO` sin ninguna línea con `cantidad_entregada > 0` pasa a `LISTO_PARA_ENTREGA`
- **THEN** el sistema responde 422 indicando que no hay entregas registradas

#### Scenario: Envío facturado no se cancela
- **WHEN** se intenta cancelar un envío con `fecha_facturado` informada
- **THEN** el sistema responde 422

### Requirement: Registro de entrega por línea
El sistema SHALL permitir registrar `cantidad_entregada` por línea mientras el envío no esté `ENTREGADO`, `CANCELADO` ni facturado. La `cantidad_entregada` MUST NOT disminuir y MAY superar `cantidad_pedida`.

#### Scenario: Entrega mayor a lo pedido
- **WHEN** se registra `cantidad_entregada = 12` en una línea con `cantidad_pedida = 10`
- **THEN** se acepta y persiste 12

#### Scenario: Entrega que disminuye
- **WHEN** se registra `cantidad_entregada = 4` en una línea que tenía 6
- **THEN** el sistema responde 422

### Requirement: Edición y borrado del envío
Un pedido (`es_remito = false`) SHALL poder editarse o borrarse solo en `PENDIENTE`. Un remito directo SHALL poder editarse (incluidas sus `cantidad_entregada`) o borrarse solo en `LISTO_PARA_ENTREGA` y sin facturar.

#### Scenario: Editar remito directo listo
- **WHEN** se edita un remito directo en `LISTO_PARA_ENTREGA` sin facturar y se cambia una línea a `cantidad_entregada = 5`
- **THEN** la línea queda con 5 y conserva su `fecha_creacion`

#### Scenario: Editar remito entregado
- **WHEN** se intenta editar un remito directo en `ENTREGADO`
- **THEN** el sistema responde 422

### Requirement: Facturación del envío
El header SHALL tener `fecha_facturado` (nullable) y `factura_referencia` (texto, nullable). El sistema SHALL exponer una operación para marcar un envío como facturado, que exige `fecha_facturado` y una `factura_referencia` no vacía. Solo se permite cuando el envío está en `LISTO_PARA_ENTREGA` o `ENTREGADO`. La misma operación con ambos valores nulos SHALL desmarcarlo. `factura_referencia` MUST NOT estar informada sin `fecha_facturado`.

#### Scenario: Marcar como facturado
- **WHEN** se factura un envío `ENTREGADO` con `fecha_facturado = 2026-10-20` y `factura_referencia = "A-0001-00001234"`
- **THEN** ambos campos quedan persistidos y el envío aparece al filtrar `facturado = true`

#### Scenario: Facturar sin referencia
- **WHEN** se factura un envío con `fecha_facturado` y `factura_referencia` vacía
- **THEN** el sistema responde 422

#### Scenario: Facturar un pedido pendiente
- **WHEN** se intenta facturar un envío en `PENDIENTE`
- **THEN** el sistema responde 422

#### Scenario: Desmarcar facturación
- **WHEN** se envían `fecha_facturado = null` y `factura_referencia = null` a un envío facturado
- **THEN** ambos campos quedan en null

### Requirement: Listado filtrable de envíos
El listado SHALL permitir filtrar por `tipo`, `cliente_id`, `sucursal_id` (destino), `origen_sucursal_id`, `estado`, `es_remito`, `facturado` (bool), `remito_legacy_id` y rango de `fecha_entrega`.

#### Scenario: Consultar solo remitos
- **WHEN** se lista con `es_remito = true`
- **THEN** solo se devuelven envíos cargados como remito directo

#### Scenario: Buscar remito anterior a la migración
- **WHEN** se lista con `remito_legacy_id = 345`
- **THEN** se devuelve el envío creado a partir del remito #345

### Requirement: Impresión del envío como remito
El detalle del envío SHALL poder imprimirse. Si el envío es un remito directo, o está en `LISTO_PARA_ENTREGA` o `ENTREGADO`, el documento impreso SHALL titularse "REMITO" con el número del envío, mostrar las cantidades entregadas y omitir las líneas con `cantidad_entregada = 0`. En cualquier otro caso SHALL titularse "PEDIDO" y mostrar las cantidades pedidas. Para `tipo = SUCURSAL`, el remito SHALL mostrar origen y destino.

#### Scenario: Imprimir pedido entregado directamente
- **WHEN** se imprime un pedido en `ENTREGADO`
- **THEN** el documento dice "REMITO N° <id>" y lista lo entregado

#### Scenario: Imprimir pedido pendiente
- **WHEN** se imprime un pedido en `PENDIENTE`
- **THEN** el documento dice "PEDIDO N° <id>" y lista lo pedido

### Requirement: Reportes de pendientes excluyen remitos directos
Los reportes de pedidos pendientes (`/pedidos-reportes/*`) MUST excluir los envíos con `es_remito = true`.

#### Scenario: Remito directo no aparece como pendiente
- **WHEN** existe un remito directo en `LISTO_PARA_ENTREGA` con fecha de entrega hoy
- **THEN** no aparece en `pendientes-por-dia` ni en `productos-pendientes-por-dia`

### Requirement: Migración de los remitos existentes
El sistema SHALL proveer un script SQL idempotente que migre todos los datos de `remitos_remito`/`remitos_remito_detalle` al modelo unificado:
- (a) Cada remito manual (sin `pedido_id`, o con `pedido_id` pero no generado automáticamente) SHALL convertirse en un envío `es_remito = true`, vinculado al id original en `pedidos_remito_legacy`. Sus líneas pasan con `cantidad_pedida = 0`, `cantidad_entregada = cantidad` y la `fecha_creacion` original. El estado se mapea `LISTO`/`EN_TRANSITO` → `LISTO_PARA_ENTREGA` y `RECIBIDO` → `ENTREGADO`. `VENTA` se mapea a `CLIENTE` y `TRANSFERENCIA` a `SUCURSAL` (origen/destino).
- (b) Cada remito generado desde un pedido SHALL absorberse sin crear envíos: solo se registra el vínculo remito → pedido en `pedidos_remito_legacy` (un pedido puede tener varios).
- (c) Los pedidos migrados del legacy con `estado_legacy=facturado` SHALL recibir `fecha_facturado` desde `costos_remitos.fecha_facturacion`.
- (d) El script MUST terminar con consultas de verificación (conteos y diferencias de cantidades) y MUST NOT borrar las tablas de origen.

#### Scenario: Remito manual migrado
- **WHEN** existe el remito #40 `VENTA`, sin pedido, `RECIBIDO`, con una línea de 6 unidades
- **THEN** tras la migración existe un envío `es_remito = true`, `tipo = CLIENTE`, `estado = ENTREGADO`, vinculado a `remito_legacy_id = 40`, con una línea `cantidad_pedida = 0`, `cantidad_entregada = 6`

#### Scenario: Remito generado absorbido
- **WHEN** existe el remito #41 generado desde el pedido #10
- **THEN** no se crea un envío nuevo, el remito #41 queda vinculado al pedido #10 y la suma de sus líneas coincide con `cantidad_remitida` del pedido #10, o aparece en la verificación de diferencias

#### Scenario: Re-ejecución
- **WHEN** el script se ejecuta dos veces
- **THEN** la segunda ejecución no crea envíos duplicados
