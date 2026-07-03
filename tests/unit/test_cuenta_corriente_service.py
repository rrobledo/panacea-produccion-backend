from datetime import date

import pytest
from fastapi import HTTPException

from app.models.proveedor import Proveedor
from app.schemas.cuenta_corriente import CuentaCorrienteProveedorCreate
from app.services import cuenta_corriente_service as service


async def _make_proveedor(session, cuit="20-11111111-1"):
    proveedor = Proveedor(nombre="Proveedor Test", cuit=cuit, fecha_alta=date.today(), estado="activo")
    session.add(proveedor)
    await session.commit()
    await session.refresh(proveedor)
    return proveedor


async def test_create_factura_cuenta_corriente_leaves_pendiente_and_default_estado(session):
    proveedor = await _make_proveedor(session)
    payload = CuentaCorrienteProveedorCreate(
        proveedor=proveedor.id,
        tipo_movimiento="FACTURA",
        numero="1",
        fecha_emision=date.today(),
        importe_total=1000,
        tipo_pago="CUENTA_CORRIENTE",
    )
    row = await service.create_cuenta_corriente(session, payload)
    assert row.importe_pendiente == 1000
    assert row.estado == "PENDIENTE"


async def test_create_factura_efectivo_is_marked_paid_immediately(session):
    proveedor = await _make_proveedor(session)
    payload = CuentaCorrienteProveedorCreate(
        proveedor=proveedor.id,
        tipo_movimiento="FACTURA",
        numero="2",
        fecha_emision=date.today(),
        importe_total=500,
        tipo_pago="EFECTIVO",
    )
    row = await service.create_cuenta_corriente(session, payload)
    assert row.importe_pendiente == 0
    assert row.estado == "PAGADO"


async def test_pago_without_factura_id_is_rejected(session):
    proveedor = await _make_proveedor(session)
    payload = CuentaCorrienteProveedorCreate(
        proveedor=proveedor.id,
        tipo_movimiento="PAGO",
        numero="3",
        fecha_emision=date.today(),
        importe_total=300,
    )
    with pytest.raises(HTTPException) as exc_info:
        await service.create_cuenta_corriente(session, payload)
    assert exc_info.value.status_code == 400


async def test_full_payment_marks_factura_and_pago_paid_via_trigger(session):
    proveedor = await _make_proveedor(session)
    factura = await service.create_cuenta_corriente(
        session,
        CuentaCorrienteProveedorCreate(
            proveedor=proveedor.id,
            tipo_movimiento="FACTURA",
            numero="10",
            fecha_emision=date.today(),
            importe_total=1000,
            tipo_pago="CUENTA_CORRIENTE",
        ),
    )
    assert factura.importe_pendiente == 1000

    pago = await service.create_cuenta_corriente(
        session,
        CuentaCorrienteProveedorCreate(
            proveedor=proveedor.id,
            tipo_movimiento="PAGO",
            numero="11",
            fecha_emision=date.today(),
            importe_total=1000,
            factura_id=factura.id,
        ),
    )

    # importe_pendiente/estado below are set by the DB trigger
    # (trg_update_importe_pendiente), not by application code.
    assert pago.importe_pendiente == 0
    assert pago.estado == "PAGADO"

    await session.refresh(factura)
    assert factura.importe_pendiente == 0
    assert factura.estado == "PAGADO"


async def test_partial_payment_leaves_factura_pendiente(session):
    proveedor = await _make_proveedor(session)
    factura = await service.create_cuenta_corriente(
        session,
        CuentaCorrienteProveedorCreate(
            proveedor=proveedor.id,
            tipo_movimiento="FACTURA",
            numero="20",
            fecha_emision=date.today(),
            importe_total=1000,
            tipo_pago="CUENTA_CORRIENTE",
        ),
    )

    await service.create_cuenta_corriente(
        session,
        CuentaCorrienteProveedorCreate(
            proveedor=proveedor.id,
            tipo_movimiento="PAGO",
            numero="21",
            fecha_emision=date.today(),
            importe_total=400,
            factura_id=factura.id,
        ),
    )

    await session.refresh(factura)
    assert factura.importe_pendiente == 600
    assert factura.estado == "PENDIENTE"


async def test_list_pagos_for_factura_returns_only_linked_payments(session):
    proveedor = await _make_proveedor(session)
    factura = await service.create_cuenta_corriente(
        session,
        CuentaCorrienteProveedorCreate(
            proveedor=proveedor.id,
            tipo_movimiento="FACTURA",
            numero="30",
            fecha_emision=date.today(),
            importe_total=1000,
            tipo_pago="CUENTA_CORRIENTE",
        ),
    )
    other_factura = await service.create_cuenta_corriente(
        session,
        CuentaCorrienteProveedorCreate(
            proveedor=proveedor.id,
            tipo_movimiento="FACTURA",
            numero="31",
            fecha_emision=date.today(),
            importe_total=200,
            tipo_pago="CUENTA_CORRIENTE",
        ),
    )
    await service.create_cuenta_corriente(
        session,
        CuentaCorrienteProveedorCreate(
            proveedor=proveedor.id,
            tipo_movimiento="PAGO",
            numero="32",
            fecha_emision=date.today(),
            importe_total=1000,
            factura_id=factura.id,
        ),
    )
    await service.create_cuenta_corriente(
        session,
        CuentaCorrienteProveedorCreate(
            proveedor=proveedor.id,
            tipo_movimiento="PAGO",
            numero="33",
            fecha_emision=date.today(),
            importe_total=200,
            factura_id=other_factura.id,
        ),
    )

    pagos = await service.list_pagos_for_factura(session, factura.id)
    assert [p.numero for p in pagos] == ["32"]
