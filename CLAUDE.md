# Estado: redesign-cuenta-corriente-proveedor (2026-07-07)

Rama actual: `redesign-cuenta-corriente-proveedor`. Todo el trabajo de esta
sección está sin commitear — ver `git status` para la lista completa de
archivos nuevos/modificados/borrados.

OpenSpec change: `openspec/changes/redesign-cuenta-corriente-proveedor/`
(proposal.md, design.md, specs/{compras,tesoreria-pagos,ordenes-compra,
libro-iva-compras,proveedores-cuenta-corriente}/spec.md, tasks.md — los 5
artefactos existen y `openspec validate redesign-cuenta-corriente-proveedor
--type change --strict --json` pasa).

## Qué es este cambio

Reemplaza el modelo plano `CuentaCorrienteProveedor` (una sola tabla
mezclando factura+pago) por un modelo normalizado tipo ERP: `Compra` /
`CompraDetalle` / `CompraImpuesto` / `CompraAdjunto`, `Pago` / `PagoMedio`
/ `PagoAplicacion`, `MovimientoCC` (ledger derivado), `OrdenCompra` /
`OrdenCompraDetalle`, y `Proveedor` extendido. Contexto completo en
`proposal.md`/`design.md` de ese change.

## Progreso: 58/58 tasks de `tasks.md` — COMPLETO

Todos los grupos (1-11) están hechos. `pytest tests/unit -q` → 111 passed.
`openspec validate --strict` pasa. Candidato a `/opsx:archive` /
`openspec archive`.

**Grupos 1-9:** schema+trigger, Proveedor extendido, Compras (incluye
`CompraDetalle.tipo` — `INSUMO`/`ITEM_GASTO`/`LIBRE`, ver detalle abajo),
Adjuntos/Vercel Blob, Tesorería/Pagos, Cuenta Corriente ledger+resumen,
Libro IVA, Órdenes de Compra, script de migración de datos.

**Grupo 10 (retiro de rutas legacy `/ctacteprov*`): COMPLETO (2026-07-07).**
El usuario confirmó que `panacea-produccion` (otro repo/deploy) ya está
deployado contra los endpoints nuevos, así que se ejecutó el cutover:
- Borrados `app/routers/cuenta_corriente.py`,
  `app/services/cuenta_corriente_service.py`, `app/schemas/cuenta_corriente.py`
  y su registro en `app/main.py` (rutas `/ctacteprov*` y `/ctacteprovresumen`
  ya no existen).
- `app/models/cuenta_corriente.py` **se mantuvo** — es la fuente read-only
  que usa `scripts/migrate_ctacteprov_to_compras.py` para leer las tablas
  legacy. Las tablas legacy en sí nunca se tocan/dropean.
- README actualizado: `/ctacteprov*` ahora dice **retirado** (no más
  "deprecado pero vivo").

**Grupo 11: COMPLETO.** 11.2 borró
`tests/unit/test_cuenta_corriente_service.py`, `test_ctacteprov_api.py`,
`test_ctacteprov_detalle_insumos.py` (protegían el código ya retirado).
11.3: `openspec validate --strict` OK, suite completa verde.

## Si se retoma este branch

El cambio está funcionalmente completo — lo único que falta es decidir si
archivar (`/opsx:archive` o `openspec archive`) y si commitear/pushear todo
lo que está sin commitear en este branch.

## Trabajo adicional post-"COMPLETO" (2026-07-09)

Encima de las 58/58 tasks originales, se agregaron dos consultas de saldo
que el `tasks.md`/specs originales no cubrían (pedido directo del usuario,
no pasó por `/opsx:propose`):

- `GET /costos/cuenta-corriente/saldos` (`movimiento_cc_service.get_saldos_por_proveedor`):
  saldo total pendiente + detalle por proveedor (`proveedor_id`,
  `proveedor_nombre`, `saldo`), agrupando `Compra.saldo_pendiente` donde
  `condicion_pago=CUENTA_CORRIENTE`, proveedores con saldo 0 se omiten.
- Filtro `con_saldo` (bool) agregado a `GET /costos/compras` — reutiliza el
  listado existente en vez de crear un endpoint de "detalle de cuenta
  corriente" separado, ya que `CompraRead` ya expone `saldo_pendiente`,
  `fecha`, `proveedor_id`. Combinar con los filtros ya existentes
  (`proveedor_id`, `fecha_desde`, `fecha_hasta`) cubre "detalle filtrable
  por comprobantes con saldo, fechas y proveedor".

Pendiente si se retoma: esto no está reflejado en
`openspec/changes/redesign-cuenta-corriente-proveedor/specs/`. Si el
change se archiva antes de decidir esto, conviene sumarlo a los specs
principales (`proveedores-cuenta-corriente`/`compras`) como parte del
archive, o abrir un change chico aparte.

Tests: `tests/unit/test_cuenta_corriente_ledger.py` (2 tests nuevos para
`/saldos`) y `tests/unit/test_compras.py` (1 test nuevo para `con_saldo`).
`pytest tests/unit -q` → 116 passed.

## Adjuntos: de Vercel Blob a bytea en la DB (2026-07-09)

Pedido explícito del usuario: revierte la decisión original de este mismo
change (`design.md`/`proposal.md`, tasks 4.x/9.5) de usar Vercel Blob como
object storage externo para los adjuntos de `Compra`. Ahora los adjuntos
se guardan como `bytea` directo en Postgres, y `Pago` gana su propio
concepto de adjuntos (antes no existía).

- `CompraAdjunto.url: Text` → `CompraAdjunto.contenido: LargeBinary`
  (`deferred=True`, igual patrón que el legacy `CuentaCorrienteProveedor.
  image`/`image2`: nunca se carga en list/detail, solo vía el endpoint de
  descarga dedicado).
- `PagoAdjunto` nuevo (`app/models/pago.py`), misma forma que
  `CompraAdjunto` (uno-a-muchos, `contenido` diferido).
- `POST /costos/compras/{id}/adjuntos` y `POST /costos/pagos/{id}/adjuntos`
  ya no dependen de ningún storage externo — reciben el archivo y lo
  guardan directo. Nuevo `GET .../adjuntos/{adjunto_id}` en ambos routers
  para descargar el binario (antes el cliente pegaba directo a la URL de
  Vercel Blob que devolvía el POST).
- **`app/services/storage_service.py` fue eliminado por completo**
  (`StorageClient`, `VercelBlobStorageClient`, `get_storage_client`,
  `StorageError`), junto con `Settings.blob_read_write_token`,
  `BLOB_READ_WRITE_TOKEN` en `.env`/README, y `vercel_blob` de
  `requirements.txt`.
- Migraciones: `migrations/0005_adjuntos_db_storage.sql` +
  `docker/init-db/09_adjuntos_db_storage.sql` (mismo par que ya existía
  para 0003/07 y 0004/08) — dropea `compras_compra_adjunto.url`, agrega
  `contenido bytea not null`, crea `compras_pago_adjunto`.
  **No hay backfill de `url`→`contenido`** para filas viejas (ninguna
  esperada todavía, ver comentario en el archivo de migración).
- `scripts/migrate_ctacteprov_to_compras.py`: ya no sube nada a Vercel
  Blob, decodifica el base64 legacy directo a bytes. Como bonus, ahora
  **también migra imágenes de filas `PAGO` legacy** a `PagoAdjunto` —
  antes se reportaban como "no migradas" porque `Pago` no tenía adjuntos
  (`pagos_con_imagen_no_migrada` en el summary ya no existe, reemplazado
  por `imagenes_migradas`). `--skip-images` sigue existiendo pero ahora es
  solo por velocidad, no por falta de credencial.

Pendiente si se retoma: `proposal.md`/`design.md` de este change todavía
describen Vercel Blob como la decisión tomada — no se reescribieron (son
el registro histórico de lo aprobado). Si se archiva, vale la pena anotar
esta reversión en los specs o en las notas de archive.

Tests: `tests/unit/test_compra_adjuntos.py` (reescrito, ya no usa un fake
storage client), `tests/unit/test_pago_adjuntos.py` (nuevo),
`tests/unit/test_migrate_ctacteprov_to_compras.py` (2 tests nuevos para
migración de imágenes). `pytest tests/unit -q` → 122 passed.

## Bug real encontrado corriendo el backfill contra datos de producción (2026-07-09)

El usuario corrió `scripts/migrate_ctacteprov_to_compras.py --apply` contra
la DB real (923 facturas, 291 pagos) y tiró 4 `saldo mismatches`. Eso
destapó un bug genuino en el script (no en el modelo/trigger): el loop que
crea `PagoAplicacion` a partir de `CuentaCorrienteProveedorAfect` descartaba
en silencio cualquier fila `Afect` cuyo `factura_id`/`pago_id` no resolviera
por una razón **distinta** de `--skip-ids` (p.ej. una fila legacy con
`tipo_movimiento` fuera de `{FACTURA, PAGO}`) — sin contador, sin log, sin
rastro. Eso es exactamente lo que produce un `saldo_pendiente` migrado más
alto de lo esperado sin ninguna pista de por qué.

Fix (mismo archivo):
- `tipo_movimiento` ahora se compara case/whitespace-insensitive
  (`.strip().upper()`), para que una variante de tipeo no caiga en el mismo
  agujero que un valor genuinamente desconocido.
- Toda fila `Afect` no resuelta por razón distinta a `--skip-ids` se
  acumula en `aplicaciones_omitidas_referencia_invalida` con diagnóstico
  (`_describe_missing_id`: distingue "no existe en la tabla" — imposible en
  este schema porque hay FK real — de "existe pero con otro
  tipo_movimiento", que es el caso real que apareció).
- Cada `saldo_mismatch` impreso ahora se cruza con esas aplicaciones no
  resueltas (mismo `factura_id`) y muestra el motivo justo al lado, en vez
  de un número pelado.
- Para mismatches sin ninguna `Afect` relacionada, se detecta el patrón
  "obtenido ≈ esperado × 10ⁿ" (error de punto decimal en el dato legacy) y
  se anota como tal; si tampoco aplica, se imprime un mensaje genérico
  indicando que `importe_pendiente` probablemente fue editado a mano sin
  pasar por el ledger `Afect`.

**Corriendo esto contra los datos reales confirmó la hipótesis**: apareció
exactamente 1 `aplicaciones omitidas (referencia inválida)` (`afect#108`,
`factura_id=377` no encontrada) — pero **ninguno de los 4 `saldo
mismatches` originales correlaciona con `factura_id=377`**. Conclusión: ese
`Afect` en particular referencia una factura que nunca se migró (no genera
`Compra`, por eso tampoco aparece en `saldo_mismatches` — ese chequeo solo
itera sobre `facturas` ya migradas). Los 4 mismatches en sí (legacy#325,
#1070, #1074, #1170) son datos legacy genuinamente inconsistentes (no un
bug de este script) — `--skip-ids` es el camino, no un fix de código.

No se re-corrió el script contra la DB real desde acá (el usuario lo corre
él mismo). Todo lo de arriba se validó con tests unitarios contra la DB de
test local, incluyendo un caso que reproduce el escenario real (`Afect`
con `factura_id` que existe pero con `tipo_movimiento` fuera de
`{FACTURA, PAGO}` — la única forma reproducible localmente, porque
`costos_cuentacorrienteproveedorafect.factura_id`/`pago_id` tienen FK real
a `costos_cuentacorrienteproveedor.id`, así que un id verdaderamente
inexistente ni siquiera se puede insertar).

Tests: `tests/unit/test_migrate_ctacteprov_to_compras.py` +3
(normalización de `tipo_movimiento`, referencia no resuelta con
diagnóstico, referencia no resuelta del lado factura sin mismatch
asociado). `pytest tests/unit -q` → 125 passed.

## Cosas a tener presentes

- DB de test local: contenedor Docker en `localhost:55432`
  (`docker compose up -d`). **Se recreó desde cero el 2026-07-07**
  (`docker compose down -v && up -d`) porque tenía drift preexistente no
  relacionado a este cambio: `articulos_final` era una VIEW real (uniendo
  `articulos`/`articulos_cp`/`articulos_cba`/`categorias`, ~1319 filas)
  en vez de la tabla-placeholder simple que define
  `docker/init-db/03_productos_costeo.sql` — rompía casi todo
  `pytest tests/unit` (107/111 tests), sin relación con compras/pagos/etc.
  Tras recrear, todos los `docker/init-db/*.sql` (incluido `07_*.sql` con
  el schema de este change) se aplican limpio y los 111 tests pasan.
- Script de backfill: `scripts/migrate_ctacteprov_to_compras.py` — dry-run
  por default, `--apply` para commitear, `--skip-images` para un run
  schema/data-only más rápido (ya no depende de ningún token externo, ver
  sección "Adjuntos" abajo). Ya se probó a mano contra la DB de test
  (dry-run + apply + verificación de saldo vía el trigger) y encontró/corrigió
  un bug real de identity-map (`populate_existing=True`). Sigue siendo
  necesario después del cutover — lee de las tablas legacy, que se
  mantienen como archivo histórico read-only.
- El fix en `app/main.py`'s `validation_exception_handler` (usar
  `jsonable_encoder` en vez de `json.dumps` crudo) fue necesario para que
  los `field_validator`/`model_validator` con `ValueError` no rompieran la
  serialización de errores 400 — no relacionado al modelo de datos en sí,
  pero forma parte de este branch.
- En este entorno `python` es Python 2.7; usar `python3` o `.venv/bin/python`
  (venv del proyecto en `.venv/`) para todo lo relacionado a esta app.
