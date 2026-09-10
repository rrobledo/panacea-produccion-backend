-- masa-procesos-y-maquinaria F2 (tasks 2.1, 2.2, 2.3): el grafo de procesos,
-- creado en paralelo al motor viejo — ver openspec/changes/masa-procesos-y-maquinaria/
-- {proposal,design}.md en el repo `panacea-produccion`.
--
-- Esta migración sólo crea estructura. Todo el llenado (naturaleza, unidad
-- base, procesos degenerados, divisiones y líneas de entrada) lo hace
-- `scripts/backfill_grafo_procesos.sql`, que se corre con psql y es idempotente:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "BEGIN;" -f scripts/backfill_grafo_procesos.sql -c "ROLLBACK;"   # dry run
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 -f scripts/backfill_grafo_procesos.sql                          # apply
--
-- Nada de acá cambia el comportamiento: la generación de órdenes sigue
-- corriendo por `costos` + `producto_base_id`. El grafo se lee sólo para
-- comparar hasta F4.
--
-- ── Sobre `articulo` ────────────────────────────────────────────────────────
-- El design.md dibuja una tabla `articulo` única y anota que `costos_insumos`
-- se unifica "gradualmente; puede quedar como vista". F2 hace la parte
-- gradual: `costos_productos` gana los campos de artículo, y `proceso_linea`
-- referencia insumo o producto con un XOR. La spec pide que una línea pueda
-- apuntar a cualquier artículo sin importar su naturaleza, y eso queda
-- satisfecho; unificar físicamente las dos tablas es una migración de datos
-- que no hace falta para construir el grafo y que arriesgaría el motor viejo,
-- que sigue leyendo `costos_insumos` directamente.
--
-- Idempotente: seguro de re-ejecutar. Uso previsto:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "BEGIN;" -f migrations/0028_grafo_procesos.sql -c "ROLLBACK;"   -- dry run
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 -f migrations/0028_grafo_procesos.sql                          -- apply for real

-- ── 2.1 · costos_productos gana los campos de artículo ──────────────────────
-- Los DEFAULT son el valor mayoritario, no el correcto: dejan la columna
-- utilizable desde el momento en que existe. El backfill los reemplaza por lo
-- que corresponde a cada producto.
ALTER TABLE costos_productos ADD COLUMN IF NOT EXISTS naturaleza VARCHAR(20) NOT NULL DEFAULT 'TERMINADO';
ALTER TABLE costos_productos ADD COLUMN IF NOT EXISTS unidad_base VARCHAR(10) NOT NULL DEFAULT 'UN';
ALTER TABLE costos_productos ADD COLUMN IF NOT EXISTS peso_unitario_g DOUBLE PRECISION;
ALTER TABLE costos_productos ADD COLUMN IF NOT EXISTS vendible BOOLEAN NOT NULL DEFAULT TRUE;
CREATE INDEX IF NOT EXISTS costos_productos_naturaleza_idx ON costos_productos (naturaleza);

-- ── 2.2 · proceso ───────────────────────────────────────────────────────────
-- Cada fila es UNA VERSIÓN. `codigo` es el identificador lógico, estable entre
-- versiones; `version` las ordena; `vigente_hasta IS NULL` marca la vigente.
-- Una orden emitida guarda el id de la versión exacta con la que se emitió, de
-- modo que editar la receta no reescriba el costo histórico (design.md D12).
CREATE TABLE IF NOT EXISTS procesos_proceso (
    id SERIAL PRIMARY KEY,
    codigo VARCHAR(50) NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    nombre VARCHAR(250) NOT NULL,
    tipo VARCHAR(20) NOT NULL,
    responsable VARCHAR(50) NOT NULL DEFAULT 'Todos',
    lote_referencia DOUBLE PRECISION NOT NULL,
    lote_unidad VARCHAR(10) NOT NULL DEFAULT 'KG',
    lote_minimo DOUBLE PRECISION,
    lote_multiplo DOUBLE PRECISION,
    minutos_setup INTEGER NOT NULL DEFAULT 0,
    vigente_desde DATE NOT NULL,
    vigente_hasta DATE
);
CREATE UNIQUE INDEX IF NOT EXISTS procesos_proceso_codigo_version_key
    ON procesos_proceso (codigo, version);
-- Una sola versión vigente por código: es la que se usa al emitir una orden.
CREATE UNIQUE INDEX IF NOT EXISTS procesos_proceso_codigo_vigente_key
    ON procesos_proceso (codigo) WHERE vigente_hasta IS NULL;

-- ── 2.3 · proceso_linea ─────────────────────────────────────────────────────
-- `insumo_id` XOR `producto_id`: una línea apunta a un artículo, y hoy los
-- artículos viven en dos tablas. El CHECK impide que apunte a los dos o a
-- ninguno, que es la forma en que este diseño se podría degradar en silencio.
CREATE TABLE IF NOT EXISTS procesos_proceso_linea (
    id SERIAL PRIMARY KEY,
    proceso_id INTEGER NOT NULL REFERENCES procesos_proceso(id) ON DELETE CASCADE,
    rol VARCHAR(20) NOT NULL,
    insumo_id INTEGER REFERENCES costos_insumos(id),
    producto_id INTEGER REFERENCES costos_productos(id),
    cantidad DOUBLE PRECISION NOT NULL,
    unidad VARCHAR(10),
    gramaje_g DOUBLE PRECISION,
    porcentaje_panadero DOUBLE PRECISION,
    merma_pct DOUBLE PRECISION NOT NULL DEFAULT 0,
    rendimiento_pct DOUBLE PRECISION NOT NULL DEFAULT 100,
    minutos_directos INTEGER NOT NULL DEFAULT 0,
    minutos_maquina INTEGER NOT NULL DEFAULT 0,
    criterio_reparto VARCHAR(10) NOT NULL DEFAULT 'PESO',
    orden INTEGER NOT NULL DEFAULT 0,
    CONSTRAINT procesos_proceso_linea_articulo_xor CHECK (
        (insumo_id IS NOT NULL AND producto_id IS NULL)
        OR (insumo_id IS NULL AND producto_id IS NOT NULL)
    )
);
CREATE INDEX IF NOT EXISTS procesos_proceso_linea_proceso_id_idx ON procesos_proceso_linea (proceso_id);
CREATE INDEX IF NOT EXISTS procesos_proceso_linea_producto_id_idx ON procesos_proceso_linea (producto_id);
CREATE INDEX IF NOT EXISTS procesos_proceso_linea_insumo_id_idx ON procesos_proceso_linea (insumo_id);

-- ── Adelanto de la tarea 5.7 ────────────────────────────────────────────────
-- La orden guardará contra qué versión de receta se emitió. La columna se crea
-- acá, nullable y sin poblar, porque la validación de versionado de la tarea
-- 2.13 necesita poder preguntar "¿alguna orden referencia esta versión?" y sin
-- la columna esa pregunta no se puede escribir ni testear. La población es de
-- F4 (tarea 5.7).
ALTER TABLE ordenes_produccion ADD COLUMN IF NOT EXISTS proceso_id INTEGER REFERENCES procesos_proceso(id);
CREATE INDEX IF NOT EXISTS ordenes_produccion_proceso_id_idx ON ordenes_produccion (proceso_id);
