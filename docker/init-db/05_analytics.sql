-- Tables for produccion-analytics (§7), confirmed via \d introspection
-- 2026-07-02. `panacea_sales_v2` is externally populated/read-only in
-- production; `planificacion2024` only needs `codigo`/`producto_id` for
-- the reference-code join this service actually performs.

CREATE TABLE costos_programacion (
    id               SERIAL PRIMARY KEY,
    responsable      VARCHAR(50) NOT NULL,
    plan             INTEGER,
    prod             INTEGER,
    producto_id      INTEGER REFERENCES costos_productos(id),
    producto_nombre  VARCHAR(255),
    fecha            DATE
);

CREATE TABLE planificacion2024 (
    codigo       INTEGER PRIMARY KEY DEFAULT 0,
    productos    VARCHAR(50),
    producto_id  INTEGER REFERENCES costos_productos(id)
);

CREATE TABLE panacea_sales_v2 (
    document_id       BIGINT,
    category_id       INTEGER,
    category          VARCHAR(50),
    ref_id            INTEGER,
    product_id        INTEGER,
    product           VARCHAR(100),
    lugar_venta_id    INTEGER,
    lugar_venta       VARCHAR(50),
    customer_id       INTEGER,
    customer          VARCHAR(50),
    operation_date    DATE,
    operation_hour    SMALLINT,
    operation_year    SMALLINT,
    operation_month   SMALLINT,
    week_of_year      VARCHAR(10),
    week_of_month     SMALLINT,
    day_of_week       SMALLINT,
    day_of_week_text  VARCHAR(20),
    count             DOUBLE PRECISION,
    subtotal          DOUBLE PRECISION
);
