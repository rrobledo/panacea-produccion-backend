-- Minimal local schema mirroring the tables this service touches in the
-- shared production Postgres instance (confirmed via \d introspection
-- 2026-07-02, see openspec/changes/produccion-costos-api/design.md).
-- Not a full copy of the production schema — only what's needed to run
-- this service's tests against a real Postgres locally instead of prod.

CREATE TABLE costos_insumos (
    id             SERIAL PRIMARY KEY,
    codigo         VARCHAR(50) NOT NULL DEFAULT '',
    nombre         VARCHAR(250) NOT NULL,
    unidad_medida  VARCHAR(10) NOT NULL DEFAULT 'GR',
    cantidad       DOUBLE PRECISION NOT NULL,
    precio         DOUBLE PRECISION NOT NULL
);

CREATE TABLE costos_proveedor (
    id          BIGSERIAL PRIMARY KEY,
    nombre      VARCHAR(255) NOT NULL,
    cuit        VARCHAR(20) NOT NULL UNIQUE,
    direccion   VARCHAR(255),
    telefono    VARCHAR(50),
    email       VARCHAR(100),
    fecha_alta  DATE NOT NULL,
    estado      VARCHAR(10) NOT NULL DEFAULT 'activo'
);

CREATE TABLE costos_cuentacorrienteproveedor (
    id                 BIGSERIAL PRIMARY KEY,
    proveedor_id       BIGINT NOT NULL REFERENCES costos_proveedor(id),
    tipo_movimiento    VARCHAR(250) NOT NULL DEFAULT 'FACTURA',
    numero             VARCHAR(50) NOT NULL,
    fecha_emision      DATE NOT NULL,
    fecha_vencimiento  DATE,
    importe_total      DOUBLE PRECISION NOT NULL,
    importe_pendiente  DOUBLE PRECISION DEFAULT 0,
    observaciones      VARCHAR(250),
    categoria          VARCHAR(250) NOT NULL DEFAULT 'MATERIA_PRIMA',
    tipo_pago          VARCHAR(250) NOT NULL DEFAULT 'CUENTA_CORRIENTE',
    caja               VARCHAR(250) NOT NULL DEFAULT 'VA',
    estado             VARCHAR(250) NOT NULL DEFAULT 'PENDIENTE',
    image              TEXT,
    image2             TEXT,
    content_type       VARCHAR(100)
);

CREATE INDEX costos_cuentacorrienteproveedor_fecha_emision_index
    ON costos_cuentacorrienteproveedor (fecha_emision);

CREATE TABLE costos_cuentacorrienteproveedorafect (
    id          BIGSERIAL PRIMARY KEY,
    importe     DOUBLE PRECISION NOT NULL,
    factura_id  BIGINT NOT NULL REFERENCES costos_cuentacorrienteproveedor(id),
    pago_id     BIGINT NOT NULL REFERENCES costos_cuentacorrienteproveedor(id)
);

-- Reproduced verbatim from production (pg_get_functiondef), 2026-07-02 —
-- see design.md "Schema Introspection Findings" for why the service must
-- not duplicate this arithmetic in application code.
CREATE OR REPLACE FUNCTION update_importe_pendiente()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE costos_cuentacorrienteproveedor
        SET importe_pendiente = importe_pendiente - NEW.importe
        WHERE id = NEW.factura_id;

        UPDATE costos_cuentacorrienteproveedor
        SET importe_pendiente = importe_pendiente - NEW.importe
        WHERE id = NEW.pago_id;
    END IF;

    IF TG_OP = 'DELETE' THEN
        UPDATE costos_cuentacorrienteproveedor
        SET importe_pendiente = importe_pendiente + OLD.importe
        WHERE id = OLD.factura_id;

        UPDATE costos_cuentacorrienteproveedor
        SET importe_pendiente = importe_pendiente + OLD.importe
        WHERE id = OLD.pago_id;
    END IF;

    IF TG_OP = 'UPDATE' THEN
        UPDATE costos_cuentacorrienteproveedor
        SET importe_pendiente = importe_pendiente + OLD.importe
        WHERE id = OLD.factura_id;

        UPDATE costos_cuentacorrienteproveedor
        SET importe_pendiente = importe_pendiente + OLD.importe
        WHERE id = OLD.pago_id;

        UPDATE costos_cuentacorrienteproveedor
        SET importe_pendiente = importe_pendiente - NEW.importe
        WHERE id = NEW.factura_id;

        UPDATE costos_cuentacorrienteproveedor
        SET importe_pendiente = importe_pendiente - NEW.importe
        WHERE id = NEW.pago_id;
    END IF;

    UPDATE costos_cuentacorrienteproveedor
    SET estado = CASE WHEN importe_pendiente <= 0 THEN 'PAGADO' ELSE 'PENDIENTE' END
    WHERE id IN (COALESCE(NEW.factura_id, OLD.factura_id));

    UPDATE costos_cuentacorrienteproveedor
    SET estado = CASE WHEN importe_pendiente <= 0 THEN 'PAGADO' ELSE 'PENDIENTE' END
    WHERE id IN (COALESCE(NEW.pago_id, OLD.pago_id));

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    ELSE
        RETURN NEW;
    END IF;
END;
$function$;

CREATE TRIGGER trg_update_importe_pendiente
AFTER INSERT OR DELETE OR UPDATE ON costos_cuentacorrienteproveedorafect
FOR EACH ROW EXECUTE FUNCTION update_importe_pendiente();
