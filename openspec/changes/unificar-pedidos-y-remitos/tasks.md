## 1. Esquema de base de datos

- [x] 1.1 Crear `migrations/0033_unificar_pedidos_remitos.sql` (idempotente, con el encabezado de uso dry run/real de las demás migraciones): `es_remito`, `origen_sucursal_id`, `fecha_facturado`, `factura_referencia` en `pedidos_pedido`, sus índices y la tabla `pedidos_remito_legacy` (design D8, pieza 1)
- [x] 1.2 Copiar la misma DDL a `docker/init-db/37_unificar_pedidos_remitos.sql`
- [x] 1.3 Aplicar la migración en la base local o de tests y verificar que la app actual sigue levantando

## 2. Script de migración de datos

- [x] 2.1 Crear `scripts/migrate_remitos_to_pedidos_unificados.sql` con el encabezado documentado (qué hace, qué no hace, heurística generado/manual, uso dry run/real), siguiendo el borrador de design D8, pieza 2
- [x] 2.2 Paso 1: vincular los remitos generados en `pedidos_remito_legacy`
- [x] 2.3 Paso 2: convertir los remitos manuales en pedidos `es_remito = true` (header + detalle agrupado por producto + vínculo legacy)
- [x] 2.4 Paso 3: completar `origen_sucursal_id` de los pedidos `SUCURSAL` existentes (remito `TRANSFERENCIA` o fábrica única)
- [x] 2.5 Paso 4: completar `fecha_facturado`/`factura_referencia` desde `costos_remitos.fecha_facturacion` para los pedidos migrados del legacy
- [x] 2.6 Paso 5: consultas de verificación (remitos sin migrar, diferencias contra `cantidad_remitida`, unidades origen vs destino, pedidos `SUCURSAL` sin origen)
- [x] 2.7 Test de integración del script: sembrar remitos manuales (`VENTA` sin pedido, `VENTA` con pedido, `TRANSFERENCIA` `EN_TRANSITO` y `RECIBIDO`, con producto duplicado), generados (en vivo y del backfill) y un pedido legacy facturado. Correr el script dos veces y verificar el resultado esperado y que no haya duplicados

## 3. Modelo y vocabulario

- [x] 3.1 `app/models/pedido.py`: agregar `es_remito`, `origen_sucursal_id` + relación `origen_sucursal` (`foreign_keys` explícitas), `fecha_facturado`, `factura_referencia`, y el modelo `PedidoRemitoLegacy` con la relación `remitos_legacy` desde `Pedido`
- [x] 3.2 Dejar de usar `cantidad_remitida` en el código (la columna sigue mapeada hasta la limpieza, o se quita del modelo con default de DB)
- [x] 3.3 `app/schemas/vocab.py`: quitar `RemitoTipo`, `RemitoEstado`, `REMITO_VALID_TRANSITIONS`, `REMITO_ESTADO_TIMESTAMP_FIELD`

## 4. Schemas Pydantic

- [x] 4.1 `PedidoCreate`: agregar `es_remito: bool = False` y `origen_sucursal_id`. Validar `es_remito` ⇒ todas las `cantidad_pedida == 0` y al menos una `cantidad_entregada > 0`
- [x] 4.2 `_PedidoTipoFieldsMixin`: `origen_sucursal_id` debe ser null con `CLIENTE` y distinto de `sucursal_id` con `SUCURSAL`
- [x] 4.3 Nuevo `PedidoFacturacionRequest` (`fecha_facturado`, `factura_referencia`): los dos informados (referencia no vacía tras trim) o los dos null
- [x] 4.4 `PedidoRead`: exponer `es_remito`, `origen_sucursal_id`, `origen_sucursal`, `fecha_facturado`, `factura_referencia`, `remitos_legacy_ids`

## 5. Servicio y routers

- [x] 5.1 `create_pedido`: para `es_remito`, persistir líneas con `cantidad_entregada`, nacer en `LISTO_PARA_ENTREGA` con `fecha_listo_para_entrega = now`. Para `SUCURSAL` sin origen, asignar la fábrica con `_get_fabrica_sucursal`
- [x] 5.2 `ensure_pendiente` → `ensure_editable`: pedido solo en `PENDIENTE`; remito directo en `LISTO_PARA_ENTREGA` sin facturar
- [x] 5.3 `update_pedido`: en un remito directo, el merge por `producto_id` actualiza `cantidad_entregada` y preserva `fecha_creacion`. Descartar las líneas con ambas cantidades en 0
- [x] 5.4 `transition_estado`: quitar `_generar_remito`. Exigir alguna `cantidad_entregada > 0` para pasar a `LISTO_PARA_ENTREGA`, bloquear la cancelación si está facturado y restringir el remito directo a `LISTO_PARA_ENTREGA → ENTREGADO`
- [x] 5.5 `registrar_entrega`: rechazar si está facturado
- [x] 5.6 Nuevo `registrar_facturacion` y endpoint `PATCH /pedidos/{id}/facturacion` (solo en `LISTO_PARA_ENTREGA`/`ENTREGADO`)
- [x] 5.7 `list_pedidos` y router: filtros `es_remito`, `facturado`, `origen_sucursal_id`, `remito_legacy_id`. Cargar `remitos_legacy` y `origen_sucursal` en `_pedido_stmt`
- [x] 5.8 `routers/pedidos_reportes.py`: excluir `es_remito` en todos los reportes de pendientes
- [x] 5.9 Eliminar `app/models/remito.py`, `app/schemas/remito.py`, `app/services/remito_service.py`, `app/routers/remitos.py` y su registro en `app/main.py`. Revisar los imports en `app/models/__init__.py`

## 6. Tests backend

- [x] 6.1 Reemplazar `tests/unit/test_remitos.py` y `tests/unit/test_pedido_genera_remito.py` por tests de remito directo (alta, validaciones, edición, transiciones, origen por defecto desde la fábrica)
- [x] 6.2 Tests de facturación (marcar, sin referencia, estado inválido, desmarcar, cancelación bloqueada, entrega bloqueada)
- [x] 6.3 Ajustar `test_pedidos.py` (sin generación de remito, regla de `LISTO_PARA_ENTREGA` sin entregas, filtros nuevos) y `test_pedidos_reportes.py` (exclusión de `es_remito`). Actualizar `tests/conftest.py` si limpia tablas de remitos
- [x] 6.4 Correr la suite completa (una corrida a la vez: la base es compartida) y dejarla en verde

## 7. Frontend `panacea-mayorista`

- [x] 7.1 `services/api.js`: quitar `remitosService` y agregar `pedidosService.facturacion(id, data)`
- [x] 7.2 Mover `RemitoCopy` a `components/remitos/EnvioPrint.jsx` con modo `REMITO`/`PEDIDO` (título, cantidades entregadas o pedidas, origen y destino para `SUCURSAL`)
- [x] 7.3 `RemitoNuevoPage`: crear con `pedidosService.create({ es_remito: true, ... })` (cliente o transferencia origen/destino) y navegar a `/pedidos/:id`
- [x] 7.4 `RemitosListPage`: listar con `pedidosService.list({ es_remito: true })`, con columnas de estado y facturación y filtro "facturado"
- [x] 7.5 `PedidoDetailPage`: quitar "Remitos generados", imprimir con `EnvioPrint` en el modo correcto, agregar el bloque "Facturación" y permitir editar `cantidad_entregada` en un remito directo editable
- [x] 7.6 Reemplazar `RemitoDetailPage` por un redirect de `/remitos/:id` (busca por `remito_legacy_id` y navega a `/pedidos/:pedidoId`). Ajustar `utils/remitosConfig.js` y `pedidosConfig.js` (estados y labels)
- [ ] 7.7 Correr lint y build con Node 22 y probar a mano: alta de remito a cliente y entre sucursales, impresión como REMITO y como PEDIDO, facturación

## 8. Despliegue y limpieza

- [ ] 8.1 Desplegar backend y frontend juntos. Correr el dry run del script de datos en producción y revisar la verificación
- [ ] 8.2 Ejecutar el script en real y guardar la salida de la verificación
- [x] 8.3 Crear `migrations/0034_drop_remitos.sql` (DROP de `remitos_remito_detalle`, `remitos_remito` y de la columna `cantidad_remitida`), para aplicarla en un despliegue posterior tras validar los datos
