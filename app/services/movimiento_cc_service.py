from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.compra import Compra
from app.models.movimiento_cc import MovimientoCC
from app.models.pago import Pago, PagoAplicacion
from app.models.proveedor import Proveedor


async def append_compra_movimiento(session: AsyncSession, compra: Compra) -> None:
    """Append a ledger row for a newly created Compra.

    Called from compra_service.create_compra in the same (uncommitted)
    transaction, for every Compra regardless of condicion_pago — the
    ledger must reflect all comprobantes so the derived proveedor balance
    stays consistent with Compra.saldo_pendiente (see design.md D1/D2).
    """
    session.add(
        MovimientoCC(
            proveedor_id=compra.proveedor_id,
            fecha=compra.fecha,
            tipo="FACTURA",
            documento=f"{compra.tipo_comprobante} {compra.numero}",
            debe=compra.total,
            haber=0,
            compra_id=compra.id,
        )
    )


async def append_pago_movimiento(session: AsyncSession, pago: Pago) -> None:
    session.add(
        MovimientoCC(
            proveedor_id=pago.proveedor_id,
            fecha=pago.fecha,
            tipo="PAGO",
            documento=f"PAGO {pago.id}",
            debe=0,
            haber=pago.importe,
            pago_id=pago.id,
        )
    )


async def get_ledger(
    session: AsyncSession,
    proveedor_id: int,
    fecha_desde: date | None,
    fecha_hasta: date | None,
) -> dict:
    proveedor = await session.get(Proveedor, proveedor_id)
    if proveedor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proveedor not found")

    stmt = select(MovimientoCC).where(MovimientoCC.proveedor_id == proveedor_id)
    if fecha_desde is not None:
        stmt = stmt.where(MovimientoCC.fecha >= fecha_desde)
    if fecha_hasta is not None:
        stmt = stmt.where(MovimientoCC.fecha <= fecha_hasta)
    stmt = stmt.order_by(MovimientoCC.fecha, MovimientoCC.id)
    rows = (await session.execute(stmt)).scalars().all()

    movimientos = []
    saldo = 0.0
    # Debe (factura) increases what's owed, Haber (pago/NC) decreases it —
    # matches the mockup's Debe/Haber/Saldo convention.
    for row in rows:
        saldo += row.debe - row.haber
        movimientos.append(
            {
                "fecha": row.fecha,
                "tipo": row.tipo,
                "documento": row.documento,
                "debe": row.debe,
                "haber": row.haber,
                "saldo": saldo,
            }
        )
    return {"proveedor_id": proveedor_id, "movimientos": movimientos}


async def get_saldos_por_proveedor(session: AsyncSession) -> dict:
    """Outstanding balance per proveedor, derived from Compra.saldo_pendiente
    (trigger-maintained, see design.md D1/D2) rather than MovimientoCC, to
    stay consistent with get_resumen's total_facturas_pendientes.
    """
    stmt = (
        select(
            Proveedor.id,
            Proveedor.nombre,
            func.sum(Compra.saldo_pendiente).label("saldo"),
        )
        .join(Compra, Compra.proveedor_id == Proveedor.id)
        .where(Compra.condicion_pago == "CUENTA_CORRIENTE")
        .group_by(Proveedor.id, Proveedor.nombre)
        .having(func.sum(Compra.saldo_pendiente) > 0)
        .order_by(Proveedor.nombre)
    )
    rows = (await session.execute(stmt)).all()

    proveedores = [
        {"proveedor_id": row.id, "proveedor_nombre": row.nombre, "saldo": float(row.saldo)} for row in rows
    ]
    total_pendiente = sum(p["saldo"] for p in proveedores)
    return {"total_pendiente": total_pendiente, "proveedores": proveedores}


async def get_gastos_por_proveedor(session: AsyncSession, fecha_desde: date, fecha_hasta: date) -> dict:
    """Compra.total per proveedor within [fecha_desde, fecha_hasta], ranked
    descending — same period scope as get_resumen's total_gastos (every
    Compra regardless of condicion_pago/estado).
    """
    if fecha_desde > fecha_hasta:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="fecha_desde must be <= fecha_hasta")

    stmt = (
        select(
            Proveedor.id,
            Proveedor.nombre,
            func.sum(Compra.total).label("total"),
        )
        .join(Compra, Compra.proveedor_id == Proveedor.id)
        .where(Compra.fecha >= fecha_desde, Compra.fecha <= fecha_hasta)
        .group_by(Proveedor.id, Proveedor.nombre)
        .order_by(func.sum(Compra.total).desc())
    )
    rows = (await session.execute(stmt)).all()

    proveedores = [
        {"proveedor_id": row.id, "proveedor_nombre": row.nombre, "total": float(row.total)} for row in rows
    ]
    total_periodo = sum(p["total"] for p in proveedores)
    return {"total_periodo": total_periodo, "proveedores": proveedores}


async def get_pagos_por_proveedor(session: AsyncSession, fecha_desde: date, fecha_hasta: date) -> dict:
    """Pago.importe per proveedor within [fecha_desde, fecha_hasta], ranked
    descending — same period scope as get_resumen's total_pagos.
    """
    if fecha_desde > fecha_hasta:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="fecha_desde must be <= fecha_hasta")

    stmt = (
        select(
            Proveedor.id,
            Proveedor.nombre,
            func.sum(Pago.importe).label("total"),
        )
        .join(Pago, Pago.proveedor_id == Proveedor.id)
        .where(Pago.fecha >= fecha_desde, Pago.fecha <= fecha_hasta)
        .group_by(Proveedor.id, Proveedor.nombre)
        .order_by(func.sum(Pago.importe).desc())
    )
    rows = (await session.execute(stmt)).all()

    proveedores = [
        {"proveedor_id": row.id, "proveedor_nombre": row.nombre, "total": float(row.total)} for row in rows
    ]
    total_periodo = sum(p["total"] for p in proveedores)
    return {"total_periodo": total_periodo, "proveedores": proveedores}


async def get_resumen(session: AsyncSession, fecha_desde: date, fecha_hasta: date) -> dict:
    if fecha_desde > fecha_hasta:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="fecha_desde must be <= fecha_hasta")

    pendientes_stmt = select(func.coalesce(func.sum(Compra.saldo_pendiente), 0.0)).where(
        Compra.condicion_pago == "CUENTA_CORRIENTE"
    )
    total_facturas_pendientes = (await session.execute(pendientes_stmt)).scalar_one()

    gastos_stmt = select(func.coalesce(func.sum(Compra.total), 0.0)).where(
        Compra.fecha >= fecha_desde, Compra.fecha <= fecha_hasta
    )
    total_gastos = (await session.execute(gastos_stmt)).scalar_one()

    pagos_stmt = select(func.coalesce(func.sum(Pago.importe), 0.0)).where(
        Pago.fecha >= fecha_desde, Pago.fecha <= fecha_hasta
    )
    total_pagos = (await session.execute(pagos_stmt)).scalar_one()

    gastos_por_categoria_stmt = (
        select(Compra.categoria, func.sum(Compra.total))
        .where(Compra.fecha >= fecha_desde, Compra.fecha <= fecha_hasta)
        .group_by(Compra.categoria)
        .having(func.sum(Compra.total) > 0)
        .order_by(func.sum(Compra.total).desc())
    )
    gastos_por_categoria = [
        {"categoria": row.categoria, "total": float(row[1])}
        for row in (await session.execute(gastos_por_categoria_stmt)).all()
    ]

    # Pago no tiene categoria propia (design.md: un Pago puede aplicarse a
    # varias Compra con categoria distinta) — se agrupa por la categoria de
    # cada Compra saldada, vía PagoAplicacion. Por eso la suma de este
    # array puede ser menor a total_pagos: un pago recién creado y todavía
    # sin aplicar contribuye a total_pagos pero no aparece acá.
    pagos_por_categoria_stmt = (
        select(Compra.categoria, func.sum(PagoAplicacion.importe))
        .join(Pago, PagoAplicacion.pago_id == Pago.id)
        .join(Compra, PagoAplicacion.compra_id == Compra.id)
        .where(Pago.fecha >= fecha_desde, Pago.fecha <= fecha_hasta)
        .group_by(Compra.categoria)
        .having(func.sum(PagoAplicacion.importe) > 0)
        .order_by(func.sum(PagoAplicacion.importe).desc())
    )
    pagos_por_categoria = [
        {"categoria": row.categoria, "total": float(row[1])}
        for row in (await session.execute(pagos_por_categoria_stmt)).all()
    ]

    return {
        "total_facturas_pendientes": float(total_facturas_pendientes),
        "total_gastos": float(total_gastos),
        "total_pagos": float(total_pagos),
        "gastos_por_categoria": gastos_por_categoria,
        "pagos_por_categoria": pagos_por_categoria,
    }
