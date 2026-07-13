-- redesign-cuenta-corriente-proveedor: creates the normalized Compras /
-- Tesorería / Órdenes de Compra schema that replaces
-- costos_cuentacorrienteproveedor* as the system of record going forward.
-- See openspec/changes/redesign-cuenta-corriente-proveedor/design.md.
--
-- Legacy tables (costos_cuentacorrienteproveedor,
-- costos_cuentacorrienteproveedorafect,
-- costos_cuentacorrienteproveedordetalle) are NOT touched by this
-- migration — they remain as read-only historical archive. This
-- migration is purely additive.
--
-- Idempotent: safe to re-run. Intended usage:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "BEGIN;" -f migrations/0003_compras_tesoreria_ordenes.sql -c "ROLLBACK;"   -- dry run
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 -f migrations/0003_compras_tesoreria_ordenes.sql                          -- apply for real

-- Proveedor: extend with fiscal/commercial fields. Nullable at the DB
-- level (existing rows have no data to backfill here) — required-on-create
-- is enforced at the Pydantic/service layer instead, matching this
-- change's existing style of app-level rather than DB-level validation.
ALTER TABLE costos_proveedor
    ADD COLUMN IF NOT EXISTS codigo           VARCHAR(50),
    ADD COLUMN IF NOT EXISTS nombre_fantasia  VARCHAR(255),
    ADD COLUMN IF NOT EXISTS condicion_iva    VARCHAR(30),
    ADD COLUMN IF NOT EXISTS condicion_pago   VARCHAR(20) NOT NULL DEFAULT 'CUENTA_CORRIENTE';

-- Órdenes de Compra (created before Compra so Compra can reference it).
CREATE TABLE IF NOT EXISTS compras_orden_compra (
    id                      BIGSERIAL PRIMARY KEY,
    proveedor_id            BIGINT NOT NULL REFERENCES costos_proveedor(id),
    numero                  VARCHAR(50) NOT NULL,
    fecha                   DATE NOT NULL,
    fecha_entrega_estimada  DATE,
    observaciones           VARCHAR(500),
    estado                  VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS compras_orden_compra_detalle (
    id                        BIGSERIAL PRIMARY KEY,
    orden_compra_id           BIGINT NOT NULL REFERENCES compras_orden_compra(id) ON DELETE CASCADE,
    descripcion               VARCHAR(500),
    insumo_id                 INTEGER REFERENCES costos_insumos(id),
    cantidad_pedida           DOUBLE PRECISION NOT NULL,
    cantidad_recibida         DOUBLE PRECISION NOT NULL DEFAULT 0,
    precio_unitario_estimado  DOUBLE PRECISION
);

CREATE INDEX IF NOT EXISTS compras_orden_compra_detalle_orden_compra_id_idx
    ON compras_orden_compra_detalle (orden_compra_id);

-- Compra (cabecera).
CREATE TABLE IF NOT EXISTS compras_compra (
    id                 BIGSERIAL PRIMARY KEY,
    proveedor_id       BIGINT NOT NULL REFERENCES costos_proveedor(id),
    orden_compra_id    BIGINT REFERENCES compras_orden_compra(id),
    tipo_comprobante   VARCHAR(20) NOT NULL,
    punto_venta        VARCHAR(20),
    numero             VARCHAR(50) NOT NULL,
    fecha              DATE NOT NULL,
    fecha_vencimiento  DATE,
    condicion_pago     VARCHAR(20) NOT NULL DEFAULT 'CUENTA_CORRIENTE',
    observaciones      VARCHAR(500),
    subtotal           DOUBLE PRECISION NOT NULL DEFAULT 0,
    iva                DOUBLE PRECISION NOT NULL DEFAULT 0,
    percepciones       DOUBLE PRECISION NOT NULL DEFAULT 0,
    impuestos          DOUBLE PRECISION NOT NULL DEFAULT 0,
    total              DOUBLE PRECISION NOT NULL DEFAULT 0,
    saldo_pendiente    DOUBLE PRECISION NOT NULL DEFAULT 0,
    estado             VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE',
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS compras_compra_fecha_idx ON compras_compra (fecha);
CREATE INDEX IF NOT EXISTS compras_compra_proveedor_id_idx ON compras_compra (proveedor_id);

-- Catalog of reusable expense concepts (e.g. "Flete", "Alquiler") that a
-- CompraDetalle line can reference instead of a costos_insumos row or a
-- free-text descripcion.
CREATE TABLE IF NOT EXISTS compras_item_gasto (
    id      BIGSERIAL PRIMARY KEY,
    codigo  VARCHAR(50),
    nombre  VARCHAR(250) NOT NULL,
    activo  BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS compras_compra_detalle (
    id                  BIGSERIAL PRIMARY KEY,
    compra_id           BIGINT NOT NULL REFERENCES compras_compra(id) ON DELETE CASCADE,
    -- Exactly one of: catalog insumo, catalog item_gasto, or free-text-only
    -- (tipo=LIBRE, both FKs null) — enforced at the Pydantic layer, same
    -- style as the rest of this change's vocabularies.
    tipo                VARCHAR(20) NOT NULL DEFAULT 'LIBRE',
    insumo_id           INTEGER REFERENCES costos_insumos(id),
    item_gasto_id       BIGINT REFERENCES compras_item_gasto(id),
    descripcion         VARCHAR(500) NOT NULL,
    cantidad            DOUBLE PRECISION NOT NULL DEFAULT 1,
    precio_unitario     DOUBLE PRECISION NOT NULL,
    descuento           DOUBLE PRECISION NOT NULL DEFAULT 0,
    alicuota_iva        DOUBLE PRECISION NOT NULL DEFAULT 0,
    importe_neto        DOUBLE PRECISION NOT NULL,
    importe_iva         DOUBLE PRECISION NOT NULL DEFAULT 0,
    importe_total       DOUBLE PRECISION NOT NULL,
    -- Reserved for a future accounting capability — no behavior yet, and
    -- no FK constraint since the referenced tables don't exist (Non-Goal
    -- in this change's design.md).
    centro_costo_id     BIGINT,
    cuenta_contable_id  BIGINT
);

CREATE INDEX IF NOT EXISTS compras_compra_detalle_compra_id_idx
    ON compras_compra_detalle (compra_id);

CREATE TABLE IF NOT EXISTS compras_compra_impuesto (
    id               BIGSERIAL PRIMARY KEY,
    compra_id        BIGINT NOT NULL REFERENCES compras_compra(id) ON DELETE CASCADE,
    tipo             VARCHAR(30) NOT NULL,
    base_imponible   DOUBLE PRECISION NOT NULL DEFAULT 0,
    porcentaje       DOUBLE PRECISION,
    importe          DOUBLE PRECISION NOT NULL
);

CREATE INDEX IF NOT EXISTS compras_compra_impuesto_compra_id_idx
    ON compras_compra_impuesto (compra_id);

CREATE TABLE IF NOT EXISTS compras_compra_adjunto (
    id          BIGSERIAL PRIMARY KEY,
    compra_id   BIGINT NOT NULL REFERENCES compras_compra(id) ON DELETE CASCADE,
    nombre      VARCHAR(255) NOT NULL,
    url         TEXT NOT NULL,
    tipo        VARCHAR(20),
    fecha       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS compras_compra_adjunto_compra_id_idx
    ON compras_compra_adjunto (compra_id);

-- Pago (cabecera) + Medios (split payment methods) + Aplicaciones (N:M
-- pago<->compra, direct generalization of
-- costos_cuentacorrienteproveedorafect).
CREATE TABLE IF NOT EXISTS compras_pago (
    id             BIGSERIAL PRIMARY KEY,
    proveedor_id   BIGINT NOT NULL REFERENCES costos_proveedor(id),
    fecha          DATE NOT NULL,
    importe        DOUBLE PRECISION NOT NULL,
    estado         VARCHAR(20) NOT NULL DEFAULT 'REGISTRADO',
    observaciones  VARCHAR(500),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS compras_pago_proveedor_id_idx ON compras_pago (proveedor_id);

CREATE TABLE IF NOT EXISTS compras_pago_medio (
    id                  BIGSERIAL PRIMARY KEY,
    pago_id             BIGINT NOT NULL REFERENCES compras_pago(id) ON DELETE CASCADE,
    tipo                VARCHAR(20) NOT NULL,
    importe             DOUBLE PRECISION NOT NULL,
    banco               VARCHAR(100),
    numero              VARCHAR(50),
    fecha_acreditacion  DATE
);

CREATE INDEX IF NOT EXISTS compras_pago_medio_pago_id_idx ON compras_pago_medio (pago_id);

CREATE TABLE IF NOT EXISTS compras_pago_aplicacion (
    id         BIGSERIAL PRIMARY KEY,
    pago_id    BIGINT NOT NULL REFERENCES compras_pago(id) ON DELETE CASCADE,
    compra_id  BIGINT NOT NULL REFERENCES compras_compra(id),
    importe    DOUBLE PRECISION NOT NULL
);

CREATE INDEX IF NOT EXISTS compras_pago_aplicacion_pago_id_idx ON compras_pago_aplicacion (pago_id);
CREATE INDEX IF NOT EXISTS compras_pago_aplicacion_compra_id_idx ON compras_pago_aplicacion (compra_id);

-- MovimientoCC: append-only ledger. Balance is never stored here — it is
-- computed at query time as a running sum ordered by (fecha, id).
CREATE TABLE IF NOT EXISTS compras_movimiento_cc (
    id            BIGSERIAL PRIMARY KEY,
    proveedor_id  BIGINT NOT NULL REFERENCES costos_proveedor(id),
    fecha         DATE NOT NULL,
    tipo          VARCHAR(20) NOT NULL,
    documento     VARCHAR(100) NOT NULL,
    debe          DOUBLE PRECISION NOT NULL DEFAULT 0,
    haber         DOUBLE PRECISION NOT NULL DEFAULT 0,
    compra_id     BIGINT REFERENCES compras_compra(id),
    pago_id       BIGINT REFERENCES compras_pago(id),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS compras_movimiento_cc_proveedor_fecha_idx
    ON compras_movimiento_cc (proveedor_id, fecha, id);

-- Trigger: PagoAplicacion insert/delete/update maintains
-- Compra.saldo_pendiente/estado. Application code must NOT duplicate this
-- arithmetic — mirrors the proven update_importe_pendiente() pattern on
-- costos_cuentacorrienteproveedorafect (see design.md D1/D2).
CREATE OR REPLACE FUNCTION update_compra_saldo_pendiente()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE compras_compra
        SET saldo_pendiente = saldo_pendiente - NEW.importe
        WHERE id = NEW.compra_id;
    END IF;

    IF TG_OP = 'DELETE' THEN
        UPDATE compras_compra
        SET saldo_pendiente = saldo_pendiente + OLD.importe
        WHERE id = OLD.compra_id;
    END IF;

    IF TG_OP = 'UPDATE' THEN
        UPDATE compras_compra
        SET saldo_pendiente = saldo_pendiente + OLD.importe
        WHERE id = OLD.compra_id;

        UPDATE compras_compra
        SET saldo_pendiente = saldo_pendiente - NEW.importe
        WHERE id = NEW.compra_id;
    END IF;

    UPDATE compras_compra
    SET estado = CASE
        WHEN saldo_pendiente <= 0 THEN 'PAGADO'
        WHEN saldo_pendiente < total THEN 'PARCIAL'
        ELSE 'PENDIENTE'
    END
    WHERE id = COALESCE(NEW.compra_id, OLD.compra_id);

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    ELSE
        RETURN NEW;
    END IF;
END;
$function$;

DROP TRIGGER IF EXISTS trg_update_compra_saldo_pendiente ON compras_pago_aplicacion;
CREATE TRIGGER trg_update_compra_saldo_pendiente
AFTER INSERT OR DELETE OR UPDATE ON compras_pago_aplicacion
FOR EACH ROW EXECUTE FUNCTION update_compra_saldo_pendiente();

