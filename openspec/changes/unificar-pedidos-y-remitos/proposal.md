## Why

Hoy un mismo movimiento de mercadería se registra en dos lugares: `pedidos_pedido`/`pedidos_pedido_detalle` (el envío: lo pedido y lo entregado) y `remitos_remito`/`remitos_remito_detalle` (el documento de despacho). Cuando un pedido llega a `LISTO_PARA_ENTREGA`/`ENTREGADO` se genera un remito que copia las cantidades entregadas. Para eso hace falta llevar la cuenta de `cantidad_remitida`, que existe solo para calcular el delta. Además, los remitos cargados a mano (venta directa o transferencia entre sucursales) viven en otra tabla, con otra máquina de estados y otras pantallas. Esa duplicación complica el código, los reportes y la operación diaria. Desde que el detalle tiene `fecha_creacion`, ya se puede distinguir un ítem del pedido original de uno agregado después, así que el detalle del pedido alcanza para representar también el remito.

## What Changes

- El pedido (`pedidos_pedido` + `pedidos_pedido_detalle`) pasa a ser la **única** entidad de envío. Un remito es un pedido cuyas líneas tienen `cantidad_entregada`.
- Nuevo flag `es_remito` en el header. Un remito cargado directamente es un pedido con `es_remito = true`, `cantidad_pedida = 0` en todas sus líneas y lo despachado en `cantidad_entregada`. Nace en `LISTO_PARA_ENTREGA`.
- El header usa el `tipo` existente (`CLIENTE` | `SUCURSAL`) para distinguir un remito a cliente de una transferencia entre sucursales. Se agrega `origen_sucursal_id`: el destino sigue siendo `sucursal_id` y el origen, si no se informa, es la sucursal `FABRICA`.
- Facturación en el header: `fecha_facturado` (nullable) y `factura_referencia` (obligatoria cuando hay fecha). Se agrega un endpoint para marcar y desmarcar el envío como facturado y un filtro `facturado` en el listado.
- La impresión del pedido sale como **REMITO** (título "REMITO", cantidades entregadas) cuando el envío es un remito directo o ya está en `LISTO_PARA_ENTREGA`/`ENTREGADO`. Si no, sale como "PEDIDO".
- **BREAKING**: dejan de generarse remitos al avanzar de estado un pedido. Se elimina la API `/costos/remitos` (listar, crear, editar, borrar, cambiar estado) y la lógica de `cantidad_remitida`.
- **BREAKING**: desaparecen los estados propios del remito (`LISTO`/`EN_TRANSITO`/`RECIBIDO`). Un remito usa los estados del pedido.
- Migración SQL (idempotente, con dry run por `BEGIN/ROLLBACK`) que pasa todos los datos actuales:
  - Los remitos manuales (sin pedido, o con un pedido pero cargados a mano) se convierten en pedidos `es_remito = true`.
  - Los remitos generados desde un pedido se absorben, porque sus cantidades ya están en `cantidad_entregada`. Se verifica la consistencia contra `cantidad_remitida`.
  - Se completa `fecha_facturado` desde `costos_remitos.fecha_facturacion` para los pedidos migrados del sistema legacy.
  - Una tabla de mapeo `pedidos_remito_legacy` (remito viejo → envío) permite encontrar los remitos ya impresos por su número anterior.
- Las tablas `remitos_remito*` y la columna `cantidad_remitida` quedan como archivo de solo lectura. Se borran en una migración posterior, una vez validados los datos.
- Frontend `panacea-mayorista`: el menú "Remitos" (nuevo y consulta) pasa a operar sobre `/pedidos` con `es_remito`. Se agrega la acción de facturar. Se quita la sección "Remitos generados" del detalle del pedido.

## Capabilities

### New Capabilities
- `envios`: entidad única de envío (pedido o remito directo, a cliente o entre sucursales). Cubre: alta y edición, cantidades pedidas/entregadas por línea, identificación de ítems agregados por `fecha_creacion`, estados, facturación (`fecha_facturado`/`factura_referencia`), impresión como remito, listado filtrable y migración de los datos de remitos existentes.

### Modified Capabilities
<!-- Las specs de pedidos/remitos viven solo en el change sin archivar `pedidos-y-remitos` (openspec/specs no tiene `pedidos` ni `remitos`). Por eso este change define la capability `envios` completa como nueva, y reemplaza las specs `pedidos` y `remitos` de ese change. -->
- (ninguna en `openspec/specs/`)

## Impact

- **Backend** (`panacea-produccion-backend`):
  - `app/models/pedido.py`, `app/schemas/pedido.py`, `app/schemas/vocab.py`, `app/services/pedido_service.py`, `app/routers/pedidos.py`, `app/routers/pedidos_reportes.py` (los reportes de pendientes excluyen `es_remito`).
  - Se eliminan `app/models/remito.py`, `app/schemas/remito.py`, `app/services/remito_service.py`, `app/routers/remitos.py` y su registro en `app/main.py`.
  - Tests: `tests/unit/test_remitos.py` y `tests/unit/test_pedido_genera_remito.py` se reemplazan. Se ajustan `test_pedidos.py` y `test_pedidos_reportes.py`.
- **DB**: nueva `migrations/0033_unificar_pedidos_remitos.sql` (+ `docker/init-db/37_...`), nuevo `scripts/migrate_remitos_to_pedidos_unificados.sql` y una migración de limpieza posterior (drop).
- **Frontend** (`panacea-mayorista`): `services/api.js`, `RemitoNuevoPage`, `RemitosListPage`, `RemitoDetailPage` (pasan a usar pedidos o se fusionan con `PedidoDetailPage`), `PedidoDetailPage` (impresión como remito, facturación), `utils/remitosConfig.js`.
- **Operación**: los números de remito impresos antes de la migración se buscan por `remito_legacy_id` (tabla `pedidos_remito_legacy`). Los remitos nuevos se numeran con el id del pedido.
