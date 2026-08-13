## Why

Hoy `Remitos`/`RemitoDetalles` (`costos_remitos`) mezclan dos conceptos en
una sola tabla: el pedido del cliente (qué se quiere, para cuándo) y el
comprobante de entrega (qué se despachó realmente), con una sola columna
`entregado` por línea y un único estado lineal `creado → ... →
facturado`. Eso no alcanza para dos necesidades nuevas: (1) trackear
entregas parciales de un pedido a lo largo de varios despachos antes de
cerrarlo, y (2) emitir remitos que no tienen ningún pedido de cliente
detrás — traslados de mercadería entre sucursales o de una sucursal a la
fábrica. El modelo actual no tiene forma de representar un remito sin
cliente, ni de generar más de un remito a partir de un mismo pedido.

## What Changes

- **BREAKING**: se reemplaza el modelo plano `Remitos`/`RemitoDetalles`
  (tabla `costos_remitos`/`costos_remitodetalles`) por dos entidades
  separadas: `Pedido`/`PedidoDetalle` (la intención de compra del
  cliente) y un `Remito`/`RemitoDetalle` rediseñado (el comprobante de
  traslado/entrega física). El router/servicio/schema `remitos` actual
  (incluyendo su compatibilidad con el contrato de
  `panacea-mayorista-backend`) se elimina; ese consumidor deberá migrar
  al nuevo contrato por separado.
- `Pedido` tiene su propio estado (`PENDIENTE → EN_PREPARACION →
  PREPARADO → LISTO_PARA_ENTREGA → ENTREGADO`, más `CANCELADO`) y cada
  `PedidoDetalle` trackea `cantidad_pedida` y `cantidad_entregada` de
  forma independiente, permitiendo que se despache en más de una tanda.
- `Remito` gana un `tipo`: `VENTA` (asociado a un cliente, con
  `pedido_id` opcional) o `TRANSFERENCIA` (traslado interno, sin
  cliente, con `origen_sucursal_id`/`destino_sucursal_id`
  obligatorios). Un remito de tipo `VENTA` puede existir sin
  `pedido_id` (venta directa, sin pedido previo).
- Cuando un `Pedido` pasa a estado `LISTO_PARA_ENTREGA` o `ENTREGADO`,
  el sistema genera automáticamente un `Remito` tipo `VENTA` con
  `pedido_id` apuntando al pedido de origen, copiando como líneas del
  remito las cantidades efectivamente entregadas (`cantidad_entregada`)
  de cada `PedidoDetalle` en ese momento.
- Nueva capability `sucursales`: catálogo simple (`id`, `nombre`,
  `tipo`: `SUCURSAL`/`FABRICA`) usado como origen/destino de los
  remitos de transferencia. Sin este catálogo no hay forma de validar
  ni reportar traslados internos.
- El estado de `Remito` pasa a ser un flujo propio de logística de
  despacho (`PENDIENTE → EN_PREPARACION → LISTO → EN_TRANSITO →
  RECIBIDO`), desacoplado del estado de `Pedido` — un remito de tipo
  `TRANSFERENCIA` nunca tiene pedido detrás y avanza por este mismo
  flujo.

## Capabilities

### New Capabilities
- `pedidos`: alta, edición, listado y ciclo de estados de la nota de
  pedido de un cliente, incluyendo entrega parcial por línea y la
  generación automática del remito de venta al llegar a
  `LISTO_PARA_ENTREGA`/`ENTREGADO`.
- `remitos`: comprobante de traslado/entrega física — tipo `VENTA`
  (con o sin pedido de origen) o `TRANSFERENCIA` (entre sucursales o
  sucursal↔fábrica), su propio ciclo de estados, y las reglas de
  edición/borrado según estado.
- `sucursales`: catálogo de sucursales y fábrica usado como
  origen/destino de remitos de transferencia.

### Modified Capabilities
(ninguna — no existe hoy un spec archivado para `remitos` en
`openspec/specs/`; el módulo actual en `app/models/remitos.py` nunca se
sincronizó a specs formales, así que este change lo introduce desde
cero como capability nueva en lugar de como delta.)

## Impact

- Código: se eliminan `app/models/remitos.py`, `app/schemas/remitos.py`,
  `app/services/remitos_service.py`, `app/routers/remitos.py`,
  `app/routers/remitos_reportes.py`, `app/schemas/remitos_reportes.py`
  y su registro en `app/main.py`. Se agregan modelos/schemas/servicios/
  routers nuevos para `Pedido`, `Remito` (rediseñado) y `Sucursal`.
- Base de datos: nuevas tablas (`pedidos_pedido`, `pedidos_pedido_detalle`,
  `remitos_remito`, `remitos_remito_detalle`, `sucursales_sucursal`);
  se dropean `costos_remitos`/`costos_remitodetalles` (sin backfill —
  ver design.md para la decisión de migración de datos existentes).
- Consumidores externos: `panacea-mayorista-backend` (u otro cliente
  que hoy pegue contra `/costos/remitos*`) pierde ese contrato y debe
  migrar a los endpoints nuevos (`/pedidos*`, `/remitos*` rediseñado).
- Reportes: `app/routers/remitos_reportes.py` actual (basado en
  `Remitos.estado`) deja de existir, reemplazado por
  `app/routers/pedidos_reportes.py` sobre `Pedido`/`PedidoDetalle` (ver
  capability `pedidos`, Requirement "Reportes de pedidos pendientes") —
  decisión tomada explícitamente durante la implementación de este
  change, no en la propuesta original.
