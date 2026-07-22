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

## Port a SQL puro del script de backfill (2026-07-20)

Pedido explícito del usuario: `scripts/migrate_ctacteprov_to_compras.sql`
(nuevo, sin commitear) es un port completo a SQL puro de
`scripts/migrate_ctacteprov_to_compras.py`, para entornos donde correr
Python contra la DB destino no es una opción. **No reemplaza el script
Python** — ambos quedan en `scripts/`, mismo comportamiento.

Diseño (ver comentarios largos al inicio del propio archivo `.sql` para el
detalle completo):
- ids nuevos se reservan de antemano via `nextval(pg_get_serial_sequence(...))`
  en dos tablas temp (`_compra_id_map`/`_pago_id_map`, legacy_id → nuevo id),
  porque `INSERT ... SELECT ... RETURNING` no puede exponer columnas del
  `FROM` de origen — necesario para que los INSERTs posteriores (detalle,
  impuesto, movimiento_cc, adjuntos, aplicaciones) puedan hacer JOIN de
  vuelta al id legacy.
- Decode de `image`/`image2` (base64) vía una función `plpgsql` temp-scoped
  (`pg_temp.b64decode_or_null`) que atrapa el error de `decode(...,
  'base64')` y devuelve NULL en vez de abortar la migración — mismo
  comportamiento que el `try/except` de `_decode_legacy_images` en Python.
- `--skip-ids` → tabla temp `_skip_ids` que el operador puebla a mano antes
  de correr el script (editando el `INSERT INTO _skip_ids VALUES (...)`
  que queda vacío por default).
- `--skip-images` → no hay flag, se indica comentar a mano las dos
  secciones "images" del archivo.
- El resumen impreso por Python se reemplaza por un bloque de `SELECT`s de
  verificación al final (resumen de conteos, filas con tipo_movimiento
  desconocido, aplicaciones omitidas por exclusión, aplicaciones omitidas
  por referencia inválida con diagnóstico, saldo_mismatches con el mismo
  heurístico de "error de punto decimal ~10ⁿx") — resultsets consultables
  desde `psql` en vez de líneas de texto, deliberadamente no es una
  traducción línea-por-línea del `print()`.
- Guard de seguridad nuevo (no existe en el script Python): un `DO` block al
  inicio aborta con `RAISE EXCEPTION` si `compras_compra` ya tiene filas,
  porque a diferencia de `migrations/000*.sql` **este script no es
  idempotente** (ids explícitos reservados de la secuencia) — correrlo dos
  veces duplicaría todo.
- Misma convención BEGIN/ROLLBACK que `migrations/0003`/`0005` para
  dry-run: `psql ... -c "BEGIN;" -f scripts/migrate_ctacteprov_to_compras.sql
  -c "ROLLBACK;"` vs `psql ... -1 -f scripts/migrate_ctacteprov_to_compras.sql`
  para aplicar.

**Verificado por paridad, no solo por lectura**: se armó un seed de datos
contra la DB de test local cubriendo cada rama de comportamiento (factura
CUENTA_CORRIENTE con detalle/iva/percepción/imagen válida+inválida, factura
CONTADO sin detalle, `tipo_movimiento` con espacios/mayúsculas variables,
`tipo_movimiento` desconocido referenciado por un Afect, pago con medio
conocido/desconocido, aplicación parcial, fila con `importe_pendiente`
editado a mano con y sin desfasaje decimal, ids excluidos vía skip-ids en
ambos lados del Afect). Se corrió el script Python y el `.sql` cada uno
exactamente una vez contra una DB recién recreada desde cero con el mismo
seed, y se comparó el contenido de las 9 tablas relevantes
(`compras_compra`, `_detalle`, `_impuesto`, `compras_pago`, `_medio`,
`_aplicacion`, `compras_movimiento_cc`, `compras_compra_adjunto`,
`compras_pago_adjunto`) fila por fila: **idénticas, incluyendo los ids
autogenerados** (ambos motores reservan ids en el mismo orden). El resumen
de verificación (conteos, diagnósticos de referencia inválida, saldo
mismatches) también coincidió exactamente entre ambos. También se probó el
guard de seguridad (aborta en la segunda corrida) y el flujo dry-run
(`BEGIN;`/`ROLLBACK;` no deja nada escrito).

## `migrate_ctacteprov_to_compras.sql`: TRUNCATE previo + pago sintético para facturas al contado (2026-07-21)

Dos pedidos explícitos del usuario, solo sobre el `.sql` (el port Python
**no** se tocó, queda desincronizado en estos dos puntos):

- El guard de seguridad `DO $$ ... RAISE EXCEPTION` que abortaba si
  `compras_compra` ya tenía filas (mencionado como probado en la sección
  anterior) **se reemplazó** por un `TRUNCATE TABLE ... RESTART IDENTITY
  CASCADE` explícito sobre las 9 tablas destino, al inicio del script. El
  script ahora es re-corrible: cada corrida arranca de cero en vez de
  abortar o duplicar. Es destructivo para cualquier fila que ya esté en
  esas tablas (ej. algo cargado a mano desde la app) — asumido aceptable
  porque el uso real es "recrear compras_* desde las tablas legacy".
- Nueva rama de negocio: factura legacy (`tipo_movimiento=FACTURA`) con
  `tipo_pago IN ('TRANSFERENCIA', 'EFECTIVO')` ahora genera, además de la
  `Compra`, un `Pago`/`PagoMedio`/`MovimientoCC` sintético (mismo
  `tipo_pago` como medio, misma fecha que la factura, por el
  `importe_total` completo) + una `PagoAplicacion` que lo aplica contra
  esa `Compra`. Antes, estas facturas se guardaban directo con
  `saldo_pendiente=0`/`estado=PAGADO` sin ningún `Pago` detrás — el ledger
  (`compras_movimiento_cc`) solo tenía el lado `FACTURA` (debe), nunca el
  `PAGO` (haber), a pesar de que la columna `saldo_pendiente` decía 0.
  Ahora `saldo_pendiente` para estas filas arranca en `importe_total` (no
  en 0) y baja a 0 vía el trigger `trg_update_compra_saldo_pendiente`
  cuando se inserta la `PagoAplicacion` sintética — mismo mecanismo que
  cualquier pago real, nada hardcodeado a mano.
  - Otros `tipo_pago` no-`CUENTA_CORRIENTE` (`CHEQUE`, `TARJETA`, vacío,
    etc.) **no** están alcanzados por este cambio — siguen yendo directo a
    `saldo_pendiente=0`/`PAGADO` sin `Pago`, igual que antes. El usuario
    pidió esto específicamente para `TRANSFERENCIA`/`EFECTIVO`.
  - Nuevo `_factura_pago_id_map` (legacy factura id → pago id sintético
    reservado), paralelo a `_compra_id_map`/`_pago_id_map`.
  - Resumen de verificación al final ganó una columna
    `facturas_contado_con_pago_generado`.

Verificado corriendo un seed a mano contra la DB de test local (dentro de
`BEGIN;`/`ROLLBACK;`, nada quedó commiteado): factura `CUENTA_CORRIENTE`
sin tocar (`saldo_pendiente`=total, `PENDIENTE`), factura `TRANSFERENCIA` y
factura `EFECTIVO` cada una con su `Pago` sintético + `PagoAplicacion` +
línea `PAGO` en `compras_movimiento_cc`, `saldo_pendiente=0`/`PAGADO` vía
trigger; factura `CHEQUE` sin cambios (directo a 0/`PAGADO`, sin `Pago`); y
una fila pre-existente en `compras_compra` (simulando una corrida previa)
efectivamente desapareció después del `TRUNCATE`.

Pendiente si se retoma: decidir si este mismo comportamiento (TRUNCATE +
pago sintético) se porta también a `migrate_ctacteprov_to_compras.py`, o si
se documenta la divergencia entre ambos scripts en sus propios headers.

## `categoria` en Pago (2026-07-21)

Pedido explícito del usuario: `Pago` gana un atributo `categoria` (string
libre, default `MATERIA_PRIMA`), el mismo campo que ya existía en el legacy
`costos_cuentacorrienteproveedor.categoria` — no hay vocab/enum, igual que
el legacy (`app/schemas/vocab.py` no lo lista).

- `app/models/pago.py`: `Pago.categoria: Mapped[str] = mapped_column(String(250),
  default="MATERIA_PRIMA")`.
- `app/schemas/pago.py`: `categoria: str = "MATERIA_PRIMA"` en `PagoBase`
  (cubre `PagoCreate`/`PagoUpdate`) y repetido en `PagoRead` (que no hereda
  de `PagoBase`).
- `app/services/pago_service.py::create_pago` pasa `categoria=payload.categoria`
  al construir el `Pago`; `update_pago` ya lo cubre solo por iterar
  `model_dump(exclude_unset=True)`.
- Migración: `migrations/0006_pago_categoria.sql` +
  `docker/init-db/10_pago_categoria.sql` (mismo par que los anteriores) —
  `ALTER TABLE compras_pago ADD COLUMN IF NOT EXISTS categoria VARCHAR(250)
  NOT NULL DEFAULT 'MATERIA_PRIMA'`.
- `scripts/migrate_ctacteprov_to_compras.sql` actualizado: los dos INSERT a
  `compras_pago` (sección "Pagos -> Pago" y la de pagos sintéticos para
  "Facturas al contado") ahora incluyen `categoria`, tomada de la
  `categoria` del propio row legacy (`l.categoria`, con
  `COALESCE(NULLIF(l.categoria, ''), 'MATERIA_PRIMA')` si viene vacía) —
  para el pago sintético de una factura al contado, es la `categoria` de
  esa misma factura legacy (no hay un row `PAGO` legacy separado detrás).
  Verificado a mano con un seed de 4 rows (`BEGIN;`/`ROLLBACK;`, nada
  quedó commiteado): pago real con categoria propia, pago real con
  categoria vacía (cae a `MATERIA_PRIMA`), factura `TRANSFERENCIA` cuyo
  pago sintético hereda la categoria de la factura.
- **`scripts/migrate_ctacteprov_to_compras.py` (el port Python) NO se
  tocó** — el usuario pidió específicamente actualizar el `.sql`. Sigue el
  mismo patrón de divergencia intencional ya documentado en la sección de
  TRUNCATE/pago sintético de más abajo.
- Test nuevo: `tests/unit/test_pagos.py::test_create_pago_categoria_defaults_and_can_be_overridden`.
  `pytest tests/unit -q` → 153 passed.

Nota: la DB de test local se recreó (`docker compose down -v && up -d`)
durante esta sesión porque tenía el mismo drift de `articulos_final`
(VIEW en vez de tabla) documentado más abajo — no relacionado a este
cambio, ya había vuelto a aparecer.

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
