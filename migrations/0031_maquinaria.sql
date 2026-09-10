-- masa-procesos-y-maquinaria F5 (tareas 6.1-6.3): maquinaria y carga del día.
--
-- Ver openspec/changes/masa-procesos-y-maquinaria/{specs/maquinaria/spec.md,
-- design.md D9-D11} en el repo `panacea-produccion`.
--
-- La distinción que sostiene el diseño: `proceso_operacion` declara un TIPO de
-- máquina y una capacidad mínima, nunca una máquina concreta. La máquina
-- concreta se resuelve al emitir la orden y se guarda en `orden_operacion`. Si
-- la receta apuntara a "Amasadora #2", cada mantenimiento obligaría a editar
-- recetas y se perdería la posibilidad de reacomodar el día (D10).
--
-- `capacidad_unidad` decide además el modo de ocupación (D11): KG, LITROS y
-- KG_HORA son exclusivos —una orden por vez—, mientras que CARROS y BANDEJAS
-- son concurrentes hasta la capacidad. Tratar todo como exclusivo subestima
-- mucho la cámara y produce falsos avisos de sobrecapacidad.
--
-- Idempotente: seguro de re-ejecutar.

CREATE TABLE IF NOT EXISTS maquinaria_maquina (
    id SERIAL PRIMARY KEY,
    codigo VARCHAR(50) NOT NULL,
    nombre VARCHAR(250) NOT NULL,
    tipo VARCHAR(30) NOT NULL,
    capacidad DOUBLE PRECISION NOT NULL,
    capacidad_unidad VARCHAR(20) NOT NULL,
    minutos_setup INTEGER NOT NULL DEFAULT 0,
    minutos_limpieza INTEGER NOT NULL DEFAULT 0,
    tarifa_hora DOUBLE PRECISION NOT NULL DEFAULT 0,
    area VARCHAR(50) NOT NULL DEFAULT 'Todos',
    estado VARCHAR(20) NOT NULL DEFAULT 'ACTIVA',
    turno_desde VARCHAR(5),
    turno_hasta VARCHAR(5)
);
CREATE UNIQUE INDEX IF NOT EXISTS maquinaria_maquina_codigo_key ON maquinaria_maquina (codigo);
CREATE INDEX IF NOT EXISTS maquinaria_maquina_tipo_idx ON maquinaria_maquina (tipo, estado);

CREATE TABLE IF NOT EXISTS procesos_proceso_operacion (
    id SERIAL PRIMARY KEY,
    proceso_id INTEGER NOT NULL REFERENCES procesos_proceso(id) ON DELETE CASCADE,
    orden INTEGER NOT NULL DEFAULT 0,
    nombre VARCHAR(250) NOT NULL,
    maquina_tipo VARCHAR(30) NOT NULL,
    capacidad_minima DOUBLE PRECISION,
    minutos_por_bacha INTEGER NOT NULL DEFAULT 0,
    minutos_por_unidad DOUBLE PRECISION NOT NULL DEFAULT 0,
    -- La cámara ocupa máquina 90 minutos y no consume operario. Sin esta
    -- distinción el costo de mano de obra se infla y la capacidad del día se
    -- subestima, las dos cosas a la vez.
    requiere_operario BOOLEAN NOT NULL DEFAULT TRUE,
    puede_solapar BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS procesos_proceso_operacion_proceso_idx ON procesos_proceso_operacion (proceso_id);

CREATE TABLE IF NOT EXISTS ordenes_produccion_operacion (
    id SERIAL PRIMARY KEY,
    orden_id INTEGER NOT NULL REFERENCES ordenes_produccion(id) ON DELETE CASCADE,
    proceso_operacion_id INTEGER REFERENCES procesos_proceso_operacion(id),
    nombre VARCHAR(250) NOT NULL,
    maquina_tipo VARCHAR(30) NOT NULL,
    -- NULL cuando ninguna máquina activa satisface la operación: la orden se
    -- emite igual y la operación queda marcada como no resuelta.
    maquina_id INTEGER REFERENCES maquinaria_maquina(id),
    bachas INTEGER NOT NULL DEFAULT 1,
    minutos INTEGER NOT NULL DEFAULT 0,
    requiere_operario BOOLEAN NOT NULL DEFAULT TRUE,
    orden INTEGER NOT NULL DEFAULT 0,
    inicio_previsto TIMESTAMPTZ,
    fin_previsto TIMESTAMPTZ,
    inicio_real TIMESTAMPTZ,
    fin_real TIMESTAMPTZ,
    estado VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE'
);
CREATE INDEX IF NOT EXISTS ordenes_produccion_operacion_orden_idx ON ordenes_produccion_operacion (orden_id);
CREATE INDEX IF NOT EXISTS ordenes_produccion_operacion_maquina_idx ON ordenes_produccion_operacion (maquina_id);
