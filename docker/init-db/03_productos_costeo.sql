-- Tables for the Productos/Costeo domain (produccion-costos-api §4),
-- confirmed via \d introspection 2026-07-02.

CREATE TABLE costos_productos (
    id                 SERIAL PRIMARY KEY,
    codigo             VARCHAR(50) NOT NULL,
    categoria          VARCHAR(250) NOT NULL DEFAULT 'PANADERIA',
    nombre             VARCHAR(250) NOT NULL,
    ref_id             VARCHAR(250),
    utilidad           DOUBLE PRECISION NOT NULL,
    precio_actual      DOUBLE PRECISION NOT NULL,
    unidad_medida      VARCHAR(10) NOT NULL DEFAULT 'GR',
    lote_produccion    INTEGER NOT NULL,
    tiempo_produccion  INTEGER NOT NULL DEFAULT 0,
    responsable        VARCHAR(50) NOT NULL DEFAULT 'Todos',
    is_producto        BOOLEAN NOT NULL DEFAULT true,
    habilitado         BOOLEAN NOT NULL DEFAULT true,
    prioridad          INTEGER NOT NULL DEFAULT 10
);

CREATE TABLE costos_productosref (
    id                 SERIAL PRIMARY KEY,
    producto_id        INTEGER NOT NULL REFERENCES costos_productos(id),
    ref_id             VARCHAR(250),
    unidad_conversion  INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE costos_costos (
    id           SERIAL PRIMARY KEY,
    producto_id  INTEGER NOT NULL REFERENCES costos_productos(id),
    insumo_id    INTEGER NOT NULL REFERENCES costos_insumos(id),
    cantidad     INTEGER NOT NULL
);

CREATE TABLE costos_planificacion (
    id           SERIAL PRIMARY KEY,
    fecha        DATE,
    plan         INTEGER,
    sistema      INTEGER,
    corregido    INTEGER,
    producto_id  INTEGER REFERENCES costos_productos(id),
    indice       DOUBLE PRECISION
);

-- Local stand-in for the `articulos_final` production VIEW (a 3-way UNION
-- over articulos/articulos_cp/articulos_cba — see design.md). The service
-- only ever queries the view's output shape, so a plain table with the
-- same columns is enough to exercise /precio_productos locally without
-- reproducing the whole legacy POS schema underneath it.
CREATE TABLE articulos_final (
    idarticulo   INTEGER,
    nombre       VARCHAR(50),
    idcategoria  INTEGER,
    categoria    VARCHAR,
    precio       NUMERIC(100, 4),
    activo       INTEGER
);
