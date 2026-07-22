-- One-time backfill: costos_cuentacorrienteproveedor* -> the new Compras/
-- Tesorería model (see openspec/changes/redesign-cuenta-corriente-proveedor/
-- design.md, Migration Plan step 3).
--
-- Pure-SQL port of scripts/migrate_ctacteprov_to_compras.py, for
-- environments where running that Python script against the target
-- database isn't an option. It reproduces the same behavior:
--   - Compra/CompraDetalle/CompraImpuesto/MovimientoCC per legacy FACTURA
--     row, Pago/PagoMedio/MovimientoCC per legacy PAGO row. Every Pago
--     (real or synthetic, see below) carries over the legacy row's own
--     categoria, falling back to 'MATERIA_PRIMA' if blank — same default as
--     the compras_pago.categoria column itself.
--   - Legacy FACTURA rows paid immediately (tipo_pago TRANSFERENCIA or
--     EFECTIVO) also get a synthetic Pago/PagoMedio/MovimientoCC + a
--     PagoAplicacion for the full importe_total, dated the same as the
--     factura — the legacy table only ever recorded these as a bare
--     tipo_pago flag with importe_pendiente already at 0, with no matching
--     PAGO row or Afect trail. See "Facturas al contado" section below.
--   - PagoAplicacion per costos_cuentacorrienteproveedorafect row whose
--     factura_id/pago_id both resolved to a migrated row (see PagoAplicacion
--     section below) — each insert fires trg_update_compra_saldo_pendiente,
--     replaying the legacy trigger's effect against the new Compra rows,
--     same as the Python script relies on. Do not compute saldo_pendiente
--     by hand anywhere in this file.
--   - image/image2 base64 blobs decoded into CompraAdjunto/PagoAdjunto,
--     skipping (not failing) any blob that isn't valid base64.
--   - A --skip-ids equivalent: populate the _skip_ids temp table below
--     before running to leave specific legacy ids out entirely.
--   - A closing set of verification SELECTs standing in for the Python
--     script's printed summary (row counts, unknown tipo_movimiento rows,
--     unresolved Afect references, saldo_pendiente mismatches). These are
--     plain queryable result sets rather than a line-by-line reproduction
--     of the Python prints, which is friendlier from psql anyway.
--
-- What this script does NOT attempt (see design.md D5 and Non-Goals, same
-- as the Python version):
--   - It does not fabricate a per-alícuota IVA/percepción split for
--     migrated rows — both amounts land in a single CompraImpuesto row
--     tagged HISTORICO_SIN_DESGLOSE.
--   - It does not delete or modify the legacy tables — they remain as
--     read-only historical archive.
--
-- Re-runnable by design: the script TRUNCATEs every compras_* target table
-- (RESTART IDENTITY CASCADE) before inserting anything, so running it
-- twice against the same database re-migrates from scratch instead of
-- aborting or duplicating rows. This is destructive to anything already
-- sitting in those tables (e.g. rows created through the app since a
-- previous run of this script) — only point it at a database where
-- compras_* is meant to be entirely derived from the legacy tables.
--
-- Usage (same BEGIN/ROLLBACK convention as migrations/0003, 0005):
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "BEGIN;" -f scripts/migrate_ctacteprov_to_compras.sql -c "ROLLBACK;"   -- dry run
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 -f scripts/migrate_ctacteprov_to_compras.sql                          -- apply for real
--
-- To exclude specific costos_cuentacorrienteproveedor ids (equivalent of
-- the Python script's --skip-ids), add them to the INSERT INTO _skip_ids
-- statement below before running.
--
-- To skip image/image2 migration entirely (equivalent of --skip-images,
-- for a faster schema/data-only run), comment out the two "CompraAdjunto
-- images" / "PagoAdjunto images" sections below.

-- Wipe every target table before migrating, so this script can be re-run
-- from a clean slate instead of aborting or duplicating data on a second
-- run. RESTART IDENTITY also resets compras_compra/compras_pago's
-- sequences, so the nextval() reservations below start from 1 every time.
-- Listing every FK-dependent table explicitly (rather than relying on
-- CASCADE to discover them) keeps this from silently wiping some future
-- table that happens to reference compras_compra/compras_pago.
TRUNCATE TABLE
    compras_pago_aplicacion,
    compras_pago_adjunto,
    compras_pago_medio,
    compras_pago,
    compras_compra_adjunto,
    compras_compra_impuesto,
    compras_compra_detalle,
    compras_movimiento_cc,
    compras_compra
RESTART IDENTITY CASCADE;

-- Session-scoped helper: same "skip a corrupt blob instead of failing the
-- whole migration" behavior as the Python script's _decode_legacy_images
-- (base64.b64decode wrapped in try/except). decode(..., 'base64') raises
-- on invalid input; this just turns that into NULL.
CREATE OR REPLACE FUNCTION pg_temp.b64decode_or_null(raw text) RETURNS bytea AS $fn$
BEGIN
    RETURN decode(raw, 'base64');
EXCEPTION WHEN OTHERS THEN
    RETURN NULL;
END;
$fn$ LANGUAGE plpgsql;

-- ids to leave out of this run entirely (equivalent of --skip-ids) — e.g.
-- rows with a known-bad importe_total or a saldo_pendiente that disagrees
-- with their Afect ledger. Reconcile and migrate them by hand separately.
-- Example: INSERT INTO _skip_ids VALUES (325), (1070), (1074), (1170);
CREATE TEMP TABLE _skip_ids (id BIGINT PRIMARY KEY);

-- Normalized snapshot of every non-excluded legacy row. tipo_norm mirrors
-- the Python script's case/whitespace-insensitive tipo_movimiento compare,
-- so a stray "Factura"/" PAGO " data-entry variant doesn't fall through
-- both the FACTURA and PAGO filters below.
CREATE TEMP TABLE _legacy AS
SELECT c.*, upper(trim(c.tipo_movimiento)) AS tipo_norm
FROM costos_cuentacorrienteproveedor c
WHERE NOT EXISTS (SELECT 1 FROM _skip_ids s WHERE s.id = c.id);

-- id-map tables: legacy costos_cuentacorrienteproveedor.id -> new row id.
-- ids are reserved up front (via nextval on the real sequence, in legacy-id
-- order) so every later INSERT can join back to these maps instead of
-- relying on RETURNING against a bulk INSERT...SELECT, which can't surface
-- the source row's legacy id.
CREATE TEMP TABLE _compra_id_map (legacy_id BIGINT PRIMARY KEY, compra_id BIGINT NOT NULL);
CREATE TEMP TABLE _pago_id_map (legacy_id BIGINT PRIMARY KEY, pago_id BIGINT NOT NULL);

-- Same idea, but for the synthetic Pago rows generated below for FACTURA
-- rows paid immediately (tipo_pago TRANSFERENCIA/EFECTIVO) — keyed by the
-- legacy FACTURA id itself, since there's no legacy PAGO row behind these.
CREATE TEMP TABLE _factura_pago_id_map (legacy_factura_id BIGINT PRIMARY KEY, pago_id BIGINT NOT NULL);

INSERT INTO _compra_id_map (legacy_id, compra_id)
SELECT id, nextval(pg_get_serial_sequence('compras_compra', 'id'))
FROM _legacy
WHERE tipo_norm = 'FACTURA'
ORDER BY id;

INSERT INTO _pago_id_map (legacy_id, pago_id)
SELECT id, nextval(pg_get_serial_sequence('compras_pago', 'id'))
FROM _legacy
WHERE tipo_norm = 'PAGO'
ORDER BY id;

INSERT INTO _factura_pago_id_map (legacy_factura_id, pago_id)
SELECT id, nextval(pg_get_serial_sequence('compras_pago', 'id'))
FROM _legacy
WHERE tipo_norm = 'FACTURA' AND tipo_pago IN ('TRANSFERENCIA', 'EFECTIVO')
ORDER BY id;

-- ==========================================================================
-- Facturas -> Compra
-- ==========================================================================

INSERT INTO compras_compra (
    id, proveedor_id, tipo_comprobante, numero, fecha, fecha_vencimiento,
    condicion_pago, observaciones, subtotal, iva, percepciones, impuestos,
    total, saldo_pendiente, estado
)
SELECT
    m.compra_id,
    l.proveedor_id,
    'GASTO', -- legacy never recorded a comprobante type
    l.numero,
    l.fecha_emision,
    l.fecha_vencimiento,
    CASE WHEN l.tipo_pago = 'CUENTA_CORRIENTE' THEN 'CUENTA_CORRIENTE' ELSE 'CONTADO' END,
    '[migrado de costos_cuentacorrienteproveedor#' || l.id || '] categoria=' || COALESCE(l.categoria, '')
        || ' caja=' || COALESCE(l.caja, '') || ' tipo_pago_original=' || COALESCE(l.tipo_pago, '')
        || CASE WHEN l.observaciones IS NOT NULL AND l.observaciones <> '' THEN ' | ' || l.observaciones ELSE '' END,
    l.importe_total - COALESCE(l.iva, 0) - COALESCE(l.percepcion, 0),
    0,
    0,
    COALESCE(l.iva, 0) + COALESCE(l.percepcion, 0),
    l.importe_total,
    -- CUENTA_CORRIENTE and immediate-payment (TRANSFERENCIA/EFECTIVO) rows
    -- both start "fully owed" here; the latter get a synthetic Pago +
    -- PagoAplicacion below whose trigger brings saldo_pendiente/estado
    -- down to 0/PAGADO, same as a real payment would. Any other tipo_pago
    -- (CHEQUE/TARJETA/etc, or blank) has no matching Pago concept in the
    -- legacy data at all, so it's settled directly to 0/PAGADO here.
    CASE WHEN l.tipo_pago IN ('CUENTA_CORRIENTE', 'TRANSFERENCIA', 'EFECTIVO') THEN l.importe_total ELSE 0 END,
    CASE WHEN l.tipo_pago IN ('CUENTA_CORRIENTE', 'TRANSFERENCIA', 'EFECTIVO') THEN 'PENDIENTE' ELSE 'PAGADO' END
FROM _legacy l
JOIN _compra_id_map m ON m.legacy_id = l.id
WHERE l.tipo_norm = 'FACTURA';

-- CompraDetalle, case A: legacy row has costos_cuentacorrienteproveedordetalle
-- lines — one CompraDetalle per legacy line, descripcion from the insumo
-- name (insumo_id has a real FK in the legacy table, so the LEFT JOIN/
-- COALESCE fallback below is defensive, matching the Python script).
INSERT INTO compras_compra_detalle (compra_id, descripcion, cantidad, precio_unitario, importe_neto, importe_total)
SELECT
    m.compra_id,
    COALESCE(i.nombre, 'Insumo #' || d.insumo_id),
    d.cantidad,
    CASE WHEN d.cantidad <> 0 THEN d.subtotal / d.cantidad ELSE d.subtotal END,
    d.subtotal,
    d.subtotal
FROM costos_cuentacorrienteproveedordetalle d
JOIN _compra_id_map m ON m.legacy_id = d.cuentacorrienteproveedor_id
LEFT JOIN costos_insumos i ON i.id = d.insumo_id;

-- CompraDetalle, case B: legacy row has no detail lines at all — a single
-- placeholder line carrying the whole subtotal, same as the Python script.
INSERT INTO compras_compra_detalle (compra_id, descripcion, cantidad, precio_unitario, importe_neto, importe_total)
SELECT
    m.compra_id,
    '[migrado] ' || COALESCE(l.categoria, ''),
    1,
    l.importe_total - COALESCE(l.iva, 0) - COALESCE(l.percepcion, 0),
    l.importe_total - COALESCE(l.iva, 0) - COALESCE(l.percepcion, 0),
    l.importe_total - COALESCE(l.iva, 0) - COALESCE(l.percepcion, 0)
FROM _legacy l
JOIN _compra_id_map m ON m.legacy_id = l.id
WHERE l.tipo_norm = 'FACTURA'
  AND NOT EXISTS (
      SELECT 1 FROM costos_cuentacorrienteproveedordetalle d WHERE d.cuentacorrienteproveedor_id = l.id
  );

-- CompraImpuesto: both iva and percepcion collapse into one
-- HISTORICO_SIN_DESGLOSE row (the original per-alícuota split was never
-- captured — see design.md D5).
INSERT INTO compras_compra_impuesto (compra_id, tipo, base_imponible, importe)
SELECT
    m.compra_id,
    'HISTORICO_SIN_DESGLOSE',
    l.importe_total - COALESCE(l.iva, 0) - COALESCE(l.percepcion, 0),
    COALESCE(l.iva, 0) + COALESCE(l.percepcion, 0)
FROM _legacy l
JOIN _compra_id_map m ON m.legacy_id = l.id
WHERE l.tipo_norm = 'FACTURA'
  AND COALESCE(l.iva, 0) + COALESCE(l.percepcion, 0) > 0;

-- MovimientoCC: one FACTURA row per Compra, regardless of condicion_pago
-- (the ledger must reflect every comprobante — see design.md D1/D2).
INSERT INTO compras_movimiento_cc (proveedor_id, fecha, tipo, documento, debe, haber, compra_id)
SELECT l.proveedor_id, l.fecha_emision, 'FACTURA', 'GASTO ' || l.numero, l.importe_total, 0, m.compra_id
FROM _legacy l
JOIN _compra_id_map m ON m.legacy_id = l.id
WHERE l.tipo_norm = 'FACTURA';

-- CompraAdjunto images: decode legacy base64 image/image2 columns.
-- b64decode_or_null skips (not fails on) an empty or corrupt blob.
INSERT INTO compras_compra_adjunto (compra_id, nombre, contenido, tipo)
SELECT m.compra_id, 'ctacteprov-' || l.id || '-image', dec.contenido, l.content_type
FROM _legacy l
JOIN _compra_id_map m ON m.legacy_id = l.id
CROSS JOIN LATERAL (SELECT pg_temp.b64decode_or_null(l.image) AS contenido) dec
WHERE l.tipo_norm = 'FACTURA'
  AND l.image IS NOT NULL AND l.image <> ''
  AND dec.contenido IS NOT NULL;

INSERT INTO compras_compra_adjunto (compra_id, nombre, contenido, tipo)
SELECT m.compra_id, 'ctacteprov-' || l.id || '-image2', dec.contenido, l.content_type
FROM _legacy l
JOIN _compra_id_map m ON m.legacy_id = l.id
CROSS JOIN LATERAL (SELECT pg_temp.b64decode_or_null(l.image2) AS contenido) dec
WHERE l.tipo_norm = 'FACTURA'
  AND l.image2 IS NOT NULL AND l.image2 <> ''
  AND dec.contenido IS NOT NULL;

-- ==========================================================================
-- Facturas al contado (tipo_pago TRANSFERENCIA/EFECTIVO) -> Pago sintético
-- ==========================================================================
-- The legacy table has no separate PAGO row or Afect link for these — the
-- purchase was paid in full on the spot, recorded only as a tipo_pago flag
-- with importe_pendiente already 0. To carry that into the new model as a
-- real Pago (so compras_movimiento_cc/compras_pago_aplicacion reflect it
-- like any other payment, instead of a Compra that's PAGADO with nothing
-- backing it), synthesize one Pago per such factura, dated the same as the
-- factura, for the full importe_total.

INSERT INTO compras_pago (id, proveedor_id, fecha, importe, categoria, estado, observaciones)
SELECT
    m.pago_id,
    l.proveedor_id,
    l.fecha_emision,
    l.importe_total,
    COALESCE(NULLIF(l.categoria, ''), 'MATERIA_PRIMA'),
    'REGISTRADO',
    '[migrado de costos_cuentacorrienteproveedor#' || l.id || '] pago generado automáticamente: factura al contado (tipo_pago=' || l.tipo_pago || ')'
FROM _legacy l
JOIN _factura_pago_id_map m ON m.legacy_factura_id = l.id
WHERE l.tipo_norm = 'FACTURA' AND l.tipo_pago IN ('TRANSFERENCIA', 'EFECTIVO');

INSERT INTO compras_pago_medio (pago_id, tipo, importe)
SELECT m.pago_id, l.tipo_pago, l.importe_total
FROM _legacy l
JOIN _factura_pago_id_map m ON m.legacy_factura_id = l.id
WHERE l.tipo_norm = 'FACTURA' AND l.tipo_pago IN ('TRANSFERENCIA', 'EFECTIVO');

-- MovimientoCC: one PAGO row per synthetic Pago, same as the real-Pago
-- section below.
INSERT INTO compras_movimiento_cc (proveedor_id, fecha, tipo, documento, debe, haber, pago_id)
SELECT l.proveedor_id, l.fecha_emision, 'PAGO', 'PAGO ' || m.pago_id, 0, l.importe_total, m.pago_id
FROM _legacy l
JOIN _factura_pago_id_map m ON m.legacy_factura_id = l.id
WHERE l.tipo_norm = 'FACTURA' AND l.tipo_pago IN ('TRANSFERENCIA', 'EFECTIVO');

-- PagoAplicacion for the full importe_total, applied against the Compra
-- created for this same legacy row above. This fires
-- trg_update_compra_saldo_pendiente, bringing that Compra's
-- saldo_pendiente/estado from importe_total/PENDIENTE (set above) down to
-- 0/PAGADO — do not compute saldo_pendiente by hand here either.
INSERT INTO compras_pago_aplicacion (pago_id, compra_id, importe)
SELECT m.pago_id, cm.compra_id, l.importe_total
FROM _legacy l
JOIN _factura_pago_id_map m ON m.legacy_factura_id = l.id
JOIN _compra_id_map cm ON cm.legacy_id = l.id
WHERE l.tipo_norm = 'FACTURA' AND l.tipo_pago IN ('TRANSFERENCIA', 'EFECTIVO');

-- ==========================================================================
-- Pagos -> Pago
-- ==========================================================================

INSERT INTO compras_pago (id, proveedor_id, fecha, importe, categoria, estado, observaciones)
SELECT
    m.pago_id,
    l.proveedor_id,
    l.fecha_emision,
    l.importe_total,
    COALESCE(NULLIF(l.categoria, ''), 'MATERIA_PRIMA'),
    'REGISTRADO',
    '[migrado de costos_cuentacorrienteproveedor#' || l.id || '] tipo_pago_original=' || COALESCE(l.tipo_pago, '')
        || CASE WHEN l.observaciones IS NOT NULL AND l.observaciones <> '' THEN ' | ' || l.observaciones ELSE '' END
FROM _legacy l
JOIN _pago_id_map m ON m.legacy_id = l.id
WHERE l.tipo_norm = 'PAGO';

-- PagoMedio: legacy tipo_pago carried over verbatim when it's a known
-- medio tipo, otherwise defaults to TRANSFERENCIA (same fallback as the
-- Python script's KNOWN_MEDIO_TIPOS / _medio_tipo_for).
INSERT INTO compras_pago_medio (pago_id, tipo, importe)
SELECT
    m.pago_id,
    CASE WHEN l.tipo_pago IN ('TRANSFERENCIA', 'CHEQUE', 'ECHEQ', 'EFECTIVO', 'TARJETA')
         THEN l.tipo_pago ELSE 'TRANSFERENCIA' END,
    l.importe_total
FROM _legacy l
JOIN _pago_id_map m ON m.legacy_id = l.id
WHERE l.tipo_norm = 'PAGO';

-- MovimientoCC: one PAGO row per Pago.
INSERT INTO compras_movimiento_cc (proveedor_id, fecha, tipo, documento, debe, haber, pago_id)
SELECT l.proveedor_id, l.fecha_emision, 'PAGO', 'PAGO ' || m.pago_id, 0, l.importe_total, m.pago_id
FROM _legacy l
JOIN _pago_id_map m ON m.legacy_id = l.id
WHERE l.tipo_norm = 'PAGO';

-- PagoAdjunto images: same decode-or-skip as CompraAdjunto above.
INSERT INTO compras_pago_adjunto (pago_id, nombre, contenido, tipo)
SELECT m.pago_id, 'ctacteprov-' || l.id || '-image', dec.contenido, l.content_type
FROM _legacy l
JOIN _pago_id_map m ON m.legacy_id = l.id
CROSS JOIN LATERAL (SELECT pg_temp.b64decode_or_null(l.image) AS contenido) dec
WHERE l.tipo_norm = 'PAGO'
  AND l.image IS NOT NULL AND l.image <> ''
  AND dec.contenido IS NOT NULL;

INSERT INTO compras_pago_adjunto (pago_id, nombre, contenido, tipo)
SELECT m.pago_id, 'ctacteprov-' || l.id || '-image2', dec.contenido, l.content_type
FROM _legacy l
JOIN _pago_id_map m ON m.legacy_id = l.id
CROSS JOIN LATERAL (SELECT pg_temp.b64decode_or_null(l.image2) AS contenido) dec
WHERE l.tipo_norm = 'PAGO'
  AND l.image2 IS NOT NULL AND l.image2 <> ''
  AND dec.contenido IS NOT NULL;

-- ==========================================================================
-- Afect -> PagoAplicacion
-- ==========================================================================

-- Only rows whose factura_id AND pago_id both resolved to a migrated row
-- get a PagoAplicacion — the INNER JOINs naturally drop any Afect row
-- referencing an id that was excluded via _skip_ids or that had a
-- tipo_movimiento outside {FACTURA, PAGO}, same net effect as the Python
-- script's compra_id_map.get(...)/pago_id_map.get(...) both returning None.
-- Each insert fires trg_update_compra_saldo_pendiente.
INSERT INTO compras_pago_aplicacion (pago_id, compra_id, importe)
SELECT pm.pago_id, cm.compra_id, a.importe
FROM costos_cuentacorrienteproveedorafect a
JOIN _pago_id_map pm ON pm.legacy_id = a.pago_id
JOIN _compra_id_map cm ON cm.legacy_id = a.factura_id;

-- ==========================================================================
-- Verification / summary (stands in for the Python script's printed
-- summary — run these as SELECTs from psql rather than parsing stdout)
-- ==========================================================================

-- Overall counts.
SELECT
    'resumen' AS reporte,
    (SELECT count(*) FROM _skip_ids) AS filas_excluidas_skip_ids,
    (SELECT count(*) FROM _compra_id_map) AS facturas_migradas,
    (SELECT count(*) FROM _pago_id_map) AS pagos_migrados,
    (SELECT count(*) FROM _factura_pago_id_map) AS facturas_contado_con_pago_generado,
    (SELECT count(*) FROM compras_pago_aplicacion) AS aplicaciones_creadas,
    (SELECT count(*) FROM compras_compra_adjunto) + (SELECT count(*) FROM compras_pago_adjunto) AS imagenes_migradas;

-- Legacy rows excluded because tipo_movimiento wasn't FACTURA/PAGO even
-- after trim/upper (no Compra or Pago was created for these).
SELECT 'tipo_movimiento_desconocido' AS reporte, l.id AS legacy_id, l.tipo_movimiento
FROM _legacy l
WHERE l.tipo_norm NOT IN ('FACTURA', 'PAGO')
ORDER BY l.id;

-- Afect rows dropped because one side referenced an id excluded via
-- _skip_ids (the other side, if migrated, still has its Compra/Pago row,
-- just without this PagoAplicacion link).
SELECT 'aplicaciones_omitidas_por_exclusion' AS reporte, count(*) AS total
FROM costos_cuentacorrienteproveedorafect a
LEFT JOIN _compra_id_map cm ON cm.legacy_id = a.factura_id
LEFT JOIN _pago_id_map pm ON pm.legacy_id = a.pago_id
WHERE (cm.compra_id IS NULL OR pm.pago_id IS NULL)
  AND (a.factura_id IN (SELECT id FROM _skip_ids) OR a.pago_id IN (SELECT id FROM _skip_ids));

-- Afect rows dropped for any OTHER reason (e.g. a tipo_movimiento typo on
-- the referenced row) — the most likely cause of a saldo_pendiente
-- mismatch below, since a real payment link failed to migrate silently.
SELECT
    'aplicacion_omitida_referencia_invalida' AS reporte,
    a.id AS afect_id,
    a.factura_id,
    a.pago_id,
    a.importe,
    CASE WHEN cm.compra_id IS NOT NULL THEN NULL
         WHEN NOT EXISTS (SELECT 1 FROM costos_cuentacorrienteproveedor x WHERE x.id = a.factura_id)
             THEN 'factura_id=' || a.factura_id || ' no existe en costos_cuentacorrienteproveedor (referencia huérfana)'
         ELSE 'factura_id=' || a.factura_id || ' existe pero tipo_movimiento=' ||
              COALESCE((SELECT x.tipo_movimiento FROM costos_cuentacorrienteproveedor x WHERE x.id = a.factura_id), 'NULL')
              || ' (no FACTURA)'
    END AS factura_diagnostico,
    CASE WHEN pm.pago_id IS NOT NULL THEN NULL
         WHEN NOT EXISTS (SELECT 1 FROM costos_cuentacorrienteproveedor x WHERE x.id = a.pago_id)
             THEN 'pago_id=' || a.pago_id || ' no existe en costos_cuentacorrienteproveedor (referencia huérfana)'
         ELSE 'pago_id=' || a.pago_id || ' existe pero tipo_movimiento=' ||
              COALESCE((SELECT x.tipo_movimiento FROM costos_cuentacorrienteproveedor x WHERE x.id = a.pago_id), 'NULL')
              || ' (no PAGO)'
    END AS pago_diagnostico
FROM costos_cuentacorrienteproveedorafect a
LEFT JOIN _compra_id_map cm ON cm.legacy_id = a.factura_id
LEFT JOIN _pago_id_map pm ON pm.legacy_id = a.pago_id
WHERE (cm.compra_id IS NULL OR pm.pago_id IS NULL)
  AND NOT (a.factura_id IN (SELECT id FROM _skip_ids) OR a.pago_id IN (SELECT id FROM _skip_ids))
ORDER BY a.id;

-- saldo_pendiente spot-check: migrated Compra.saldo_pendiente (post-trigger)
-- vs. the legacy importe_pendiente each CUENTA_CORRIENTE factura was
-- derived from, plus a decimal-shift hint and a count of unresolved Afect
-- rows against the same factura_id (almost always the actual cause — see
-- the report above).
SELECT
    'saldo_mismatch' AS reporte,
    l.id AS legacy_factura_id,
    COALESCE(l.importe_pendiente, 0) AS esperado,
    c.saldo_pendiente AS obtenido,
    (
        SELECT count(*) FROM costos_cuentacorrienteproveedorafect a2
        LEFT JOIN _compra_id_map cm2 ON cm2.legacy_id = a2.factura_id
        LEFT JOIN _pago_id_map pm2 ON pm2.legacy_id = a2.pago_id
        WHERE a2.factura_id = l.id
          AND (cm2.compra_id IS NULL OR pm2.pago_id IS NULL)
          AND NOT (a2.factura_id IN (SELECT id FROM _skip_ids) OR a2.pago_id IN (SELECT id FROM _skip_ids))
    ) AS aplicaciones_no_migradas_relacionadas,
    CASE
        WHEN COALESCE(l.importe_pendiente, 0) <> 0
             AND abs(round(c.saldo_pendiente / l.importe_pendiente) - (c.saldo_pendiente / l.importe_pendiente)) < 1e-6
             AND abs(round(c.saldo_pendiente / l.importe_pendiente)) IN (1000, 10000, 100000, 1000000)
            THEN 'obtenido es ~' || round(c.saldo_pendiente / l.importe_pendiente) || 'x esperado: probable error de punto decimal en el dato legacy'
        ELSE NULL
    END AS hint
FROM _legacy l
JOIN _compra_id_map m ON m.legacy_id = l.id
JOIN compras_compra c ON c.id = m.compra_id
WHERE l.tipo_pago = 'CUENTA_CORRIENTE'
  AND abs(c.saldo_pendiente - COALESCE(l.importe_pendiente, 0)) > 0.01
ORDER BY l.id;
