import base64
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import undefer

from app.models.compra import Compra, CompraAdjunto
from app.models.cuenta_corriente import (
    CuentaCorrienteProveedor,
    CuentaCorrienteProveedorAfect,
    CuentaCorrienteProveedorDetalle,
)
from app.models.insumos import Insumos
from app.models.pago import Pago, PagoAdjunto
from app.models.proveedor import Proveedor
from scripts.migrate_ctacteprov_to_compras import migrate


async def test_migrate_facturas_pagos_and_afect_preserving_saldo(session):
    proveedor = Proveedor(nombre="Legacy SA", cuit="20-1-1", fecha_alta=date.today(), estado="activo")
    session.add(proveedor)
    await session.flush()

    insumo = Insumos(codigo="H1", nombre="Harina", unidad_medida="KG", cantidad=1, precio=100)
    session.add(insumo)
    await session.flush()

    factura_pagada = CuentaCorrienteProveedor(
        proveedor_id=proveedor.id,
        tipo_movimiento="FACTURA",
        numero="F1",
        fecha_emision=date(2026, 5, 1),
        importe_total=1210,
        importe_pendiente=1210,
        categoria="MATERIA_PRIMA",
        tipo_pago="CUENTA_CORRIENTE",
        caja="VA",
        estado="PENDIENTE",
        iva=210,
        percepcion=30,
    )
    session.add(factura_pagada)
    await session.flush()
    session.add(
        CuentaCorrienteProveedorDetalle(
            cuentacorrienteproveedor_id=factura_pagada.id, insumo_id=insumo.id, cantidad=10, subtotal=970
        )
    )

    pago = CuentaCorrienteProveedor(
        proveedor_id=proveedor.id,
        tipo_movimiento="PAGO",
        numero="P1",
        fecha_emision=date(2026, 5, 10),
        importe_total=1210,
        importe_pendiente=1210,
        categoria="MATERIA_PRIMA",
        tipo_pago="TRANSFERENCIA",
        caja="VA",
        estado="PENDIENTE",
    )
    session.add(pago)
    await session.flush()
    session.add(CuentaCorrienteProveedorAfect(factura_id=factura_pagada.id, pago_id=pago.id, importe=1210))

    factura_pendiente = CuentaCorrienteProveedor(
        proveedor_id=proveedor.id,
        tipo_movimiento="FACTURA",
        numero="F2",
        fecha_emision=date(2026, 5, 15),
        importe_total=500,
        importe_pendiente=500,
        categoria="SERVICIOS",
        tipo_pago="CUENTA_CORRIENTE",
        caja="VA",
        estado="PENDIENTE",
        iva=0,
        percepcion=0,
    )
    session.add(factura_pendiente)
    await session.flush()

    summary = await migrate(session)
    await session.commit()

    assert summary["facturas_migradas"] == 2
    assert summary["pagos_migrados"] == 1
    assert summary["aplicaciones_creadas"] == 1
    assert summary["saldo_mismatches"] == []

    compras = (await session.execute(Compra.__table__.select())).fetchall()
    by_numero = {row.numero: row for row in compras}

    assert by_numero["F1"].total == 1210
    assert by_numero["F1"].subtotal == 970
    assert by_numero["F1"].impuestos == 240
    assert by_numero["F1"].saldo_pendiente == 0
    assert by_numero["F1"].estado == "PAGADO"

    assert by_numero["F2"].total == 500
    assert by_numero["F2"].saldo_pendiente == 500
    assert by_numero["F2"].estado == "PENDIENTE"


async def test_migrate_decodes_legacy_images_into_db_stored_adjuntos(session):
    proveedor = Proveedor(nombre="Legacy Imagenes SA", cuit="20-2-2", fecha_alta=date.today(), estado="activo")
    session.add(proveedor)
    await session.flush()

    factura_content = b"factura-image-bytes"
    pago_content = b"pago-image-bytes"

    factura = CuentaCorrienteProveedor(
        proveedor_id=proveedor.id,
        tipo_movimiento="FACTURA",
        numero="F1",
        fecha_emision=date(2026, 5, 1),
        importe_total=1000,
        importe_pendiente=1000,
        categoria="MATERIA_PRIMA",
        tipo_pago="CUENTA_CORRIENTE",
        caja="VA",
        estado="PENDIENTE",
        image=base64.b64encode(factura_content).decode(),
        content_type="image/jpeg",
    )
    session.add(factura)

    pago = CuentaCorrienteProveedor(
        proveedor_id=proveedor.id,
        tipo_movimiento="PAGO",
        numero="P1",
        fecha_emision=date(2026, 5, 10),
        importe_total=1000,
        importe_pendiente=1000,
        categoria="MATERIA_PRIMA",
        tipo_pago="TRANSFERENCIA",
        caja="VA",
        estado="PENDIENTE",
        image=base64.b64encode(pago_content).decode(),
        content_type="image/png",
    )
    session.add(pago)
    await session.flush()

    summary = await migrate(session)
    await session.commit()

    assert summary["imagenes_migradas"] == 2

    compra_id = (await session.execute(select(Compra.id).where(Compra.numero == "F1"))).scalar_one()
    compra_adjunto = (
        await session.execute(
            select(CompraAdjunto)
            .options(undefer(CompraAdjunto.contenido))
            .where(CompraAdjunto.compra_id == compra_id)
        )
    ).scalar_one()
    assert compra_adjunto.contenido == factura_content
    assert compra_adjunto.tipo == "image/jpeg"

    pago_id = (await session.execute(select(Pago.id))).scalar_one()
    pago_adjunto = (
        await session.execute(
            select(PagoAdjunto).options(undefer(PagoAdjunto.contenido)).where(PagoAdjunto.pago_id == pago_id)
        )
    ).scalar_one()
    assert pago_adjunto.contenido == pago_content
    assert pago_adjunto.tipo == "image/png"


async def test_migrate_skip_images_omits_adjuntos(session):
    proveedor = Proveedor(nombre="Legacy Skip SA", cuit="20-3-3", fecha_alta=date.today(), estado="activo")
    session.add(proveedor)
    await session.flush()

    factura = CuentaCorrienteProveedor(
        proveedor_id=proveedor.id,
        tipo_movimiento="FACTURA",
        numero="F1",
        fecha_emision=date(2026, 5, 1),
        importe_total=1000,
        importe_pendiente=1000,
        categoria="MATERIA_PRIMA",
        tipo_pago="CUENTA_CORRIENTE",
        caja="VA",
        estado="PENDIENTE",
        image=base64.b64encode(b"skip-me").decode(),
        content_type="image/jpeg",
    )
    session.add(factura)
    await session.flush()

    summary = await migrate(session, skip_images=True)
    await session.commit()

    assert summary["imagenes_migradas"] == 0
    adjuntos = (await session.execute(select(CompraAdjunto))).scalars().all()
    assert adjuntos == []


async def test_migrate_normalizes_tipo_movimiento_case_and_whitespace(session):
    """A stray " Factura " / "pago" variant must still migrate — previously
    it silently fell through both the FACTURA and PAGO filters, producing
    no Compra/Pago and no error.
    """
    proveedor = Proveedor(nombre="Legacy Casing SA", cuit="20-4-4", fecha_alta=date.today(), estado="activo")
    session.add(proveedor)
    await session.flush()

    factura = CuentaCorrienteProveedor(
        proveedor_id=proveedor.id,
        tipo_movimiento=" Factura ",
        numero="F1",
        fecha_emision=date(2026, 5, 1),
        importe_total=1000,
        # Full amount, not pre-netted: inserting the Afect below fires the
        # legacy update_importe_pendiente() trigger, which decrements this
        # live — same pattern as test_migrate_facturas_pagos_and_afect_preserving_saldo.
        importe_pendiente=1000,
        categoria="MATERIA_PRIMA",
        tipo_pago="CUENTA_CORRIENTE",
        caja="VA",
        estado="PENDIENTE",
    )
    session.add(factura)
    pago = CuentaCorrienteProveedor(
        proveedor_id=proveedor.id,
        tipo_movimiento="pago",
        numero="P1",
        fecha_emision=date(2026, 5, 10),
        importe_total=400,
        importe_pendiente=400,
        categoria="MATERIA_PRIMA",
        tipo_pago="TRANSFERENCIA",
        caja="VA",
        estado="PENDIENTE",
    )
    session.add(pago)
    await session.flush()
    session.add(CuentaCorrienteProveedorAfect(factura_id=factura.id, pago_id=pago.id, importe=400))

    summary = await migrate(session)
    await session.commit()

    assert summary["facturas_migradas"] == 1
    assert summary["pagos_migrados"] == 1
    assert summary["aplicaciones_creadas"] == 1
    assert summary["filas_tipo_movimiento_desconocido"] == []
    assert summary["saldo_mismatches"] == []


async def test_migrate_reports_unresolved_afect_reference(session):
    """An Afect row pointing at a legacy row with a genuinely unrecognized
    tipo_movimiento must surface in aplicaciones_omitidas_referencia_invalida
    and be cross-referenced from the resulting saldo mismatch, instead of
    disappearing silently.
    """
    proveedor = Proveedor(nombre="Legacy Bad Ref SA", cuit="20-5-5", fecha_alta=date.today(), estado="activo")
    session.add(proveedor)
    await session.flush()

    factura = CuentaCorrienteProveedor(
        proveedor_id=proveedor.id,
        tipo_movimiento="FACTURA",
        numero="F1",
        fecha_emision=date(2026, 5, 1),
        importe_total=1000,
        # Full amount; the Afect insert below fires the legacy trigger and
        # decrements this to 0 live, simulating "legacy already recorded
        # this as fully paid" — see comment on the previous test.
        importe_pendiente=1000,
        categoria="MATERIA_PRIMA",
        tipo_pago="CUENTA_CORRIENTE",
        caja="VA",
        estado="PENDIENTE",
    )
    session.add(factura)
    nota_credito = CuentaCorrienteProveedor(
        proveedor_id=proveedor.id,
        tipo_movimiento="NOTA_CREDITO",  # not FACTURA/PAGO -> never migrated
        numero="NC1",
        fecha_emision=date(2026, 5, 10),
        importe_total=1000,
        importe_pendiente=1000,
        categoria="MATERIA_PRIMA",
        tipo_pago="TRANSFERENCIA",
        caja="VA",
        estado="PENDIENTE",
    )
    session.add(nota_credito)
    await session.flush()
    # ...because this Afect "paid" it, but the other side never gets a Pago row.
    session.add(CuentaCorrienteProveedorAfect(factura_id=factura.id, pago_id=nota_credito.id, importe=1000))

    summary = await migrate(session)
    await session.commit()

    assert summary["filas_tipo_movimiento_desconocido"] == [(nota_credito.id, "NOTA_CREDITO")]
    assert summary["aplicaciones_creadas"] == 0
    assert len(summary["aplicaciones_omitidas_referencia_invalida"]) == 1
    omitida = summary["aplicaciones_omitidas_referencia_invalida"][0]
    assert omitida["factura_id"] == factura.id
    assert omitida["pago_id"] == nota_credito.id
    assert omitida["pago_no_encontrado"] is True
    assert omitida["factura_no_encontrada"] is False
    assert omitida["factura_diagnostico"] is None
    assert "tipo_movimiento='NOTA_CREDITO'" in omitida["pago_diagnostico"]


async def test_migrate_reports_unresolved_factura_side_reference(session):
    """Mirrors a real case found against production data: an Afect row
    whose factura_id resolves to a row that exists but has a
    tipo_movimiento outside {FACTURA, PAGO} — costos_cuentacorrienteproveedorafect
    has a real FK to costos_cuentacorrienteproveedor.id, so a truly
    nonexistent id can't be inserted at all; "exists with the wrong type"
    is the realistic failure mode. Since no Compra is ever created for
    that factura_id, this issue is invisible in saldo_mismatches — the
    warning is the only signal.
    """
    proveedor = Proveedor(nombre="Legacy Bad Type SA", cuit="20-6-6", fecha_alta=date.today(), estado="activo")
    session.add(proveedor)
    await session.flush()

    ajuste = CuentaCorrienteProveedor(
        proveedor_id=proveedor.id,
        tipo_movimiento="AJUSTE",  # not FACTURA/PAGO -> never migrated
        numero="AJ1",
        fecha_emision=date(2026, 5, 1),
        importe_total=1000,
        importe_pendiente=1000,
        categoria="MATERIA_PRIMA",
        tipo_pago="CUENTA_CORRIENTE",
        caja="VA",
        estado="PENDIENTE",
    )
    session.add(ajuste)
    pago = CuentaCorrienteProveedor(
        proveedor_id=proveedor.id,
        tipo_movimiento="PAGO",
        numero="P1",
        fecha_emision=date(2026, 5, 10),
        importe_total=1000,
        importe_pendiente=1000,
        categoria="MATERIA_PRIMA",
        tipo_pago="TRANSFERENCIA",
        caja="VA",
        estado="PENDIENTE",
    )
    session.add(pago)
    await session.flush()
    session.add(CuentaCorrienteProveedorAfect(factura_id=ajuste.id, pago_id=pago.id, importe=1000))

    summary = await migrate(session)
    await session.commit()

    assert summary["filas_tipo_movimiento_desconocido"] == [(ajuste.id, "AJUSTE")]
    assert len(summary["aplicaciones_omitidas_referencia_invalida"]) == 1
    omitida = summary["aplicaciones_omitidas_referencia_invalida"][0]
    assert omitida["factura_id"] == ajuste.id
    assert omitida["factura_no_encontrada"] is True
    assert omitida["pago_no_encontrado"] is False
    assert "tipo_movimiento='AJUSTE'" in omitida["factura_diagnostico"]

    # No Compra was ever created for ajuste.id, so there's nothing to
    # spot-check saldo_pendiente against — invisible in saldo_mismatches.
    assert summary["saldo_mismatches"] == []
