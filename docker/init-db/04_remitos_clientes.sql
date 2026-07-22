-- Clientes/Remitos domain (produccion-costos-api §5), confirmed via \d
-- introspection 2026-07-02. `clientes` is the real (managed=False in
-- Django) legacy table — only the columns this service touches are
-- modeled here, not the full ~48-column production table. Extended
-- 2026-07-16 (merge-mayorista-remitos-api) with the additional columns
-- ClienteRead now exposes for parity with panacea-mayorista-backend's
-- ClienteSchema.

CREATE TABLE clientes (
    idcliente        INTEGER PRIMARY KEY,
    nom1             VARCHAR(100),
    nom2             VARCHAR(100),
    cuit             VARCHAR(20),
    direccion        VARCHAR(255),
    localidad        VARCHAR(100),
    provincia        VARCHAR(50),
    tel1             VARCHAR(20),
    celular          VARCHAR(20),
    email1           VARCHAR(50),
    personacontacto  VARCHAR(255),
    activo           SMALLINT
);

CREATE TABLE costos_remitos (
    id                 SERIAL PRIMARY KEY,
    cliente_id         INTEGER REFERENCES clientes(idcliente),
    observaciones      VARCHAR(1000),
    vendedor           VARCHAR(255) NOT NULL,
    fecha_carga        TIMESTAMPTZ NOT NULL,
    fecha_entrega      TIMESTAMPTZ NOT NULL,
    fecha_preparacion  TIMESTAMPTZ,
    fecha_listo        TIMESTAMPTZ,
    fecha_despacho     TIMESTAMPTZ,
    fecha_recibido     TIMESTAMPTZ,
    fecha_facturacion  TIMESTAMPTZ
);

CREATE TABLE costos_remitodetalles (
    id             SERIAL PRIMARY KEY,
    remito_id      INTEGER REFERENCES costos_remitos(id),
    producto_id    INTEGER NOT NULL REFERENCES costos_productos(id),
    cantidad       INTEGER NOT NULL,
    entregado      INTEGER,
    observaciones  VARCHAR(1000)
);
