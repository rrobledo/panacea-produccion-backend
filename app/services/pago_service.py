from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, undefer

from app.models.compra import Compra
from app.models.pago import Pago, PagoAdjunto, PagoAplicacion, PagoMedio
from app.models.proveedor import Proveedor
from app.schemas.pago import PagoAplicacionCreate, PagoCreate, PagoUpdate
from app.services import movimiento_cc_service


async def _get_proveedor_or_404(session: AsyncSession, proveedor_id: int) -> Proveedor:
    proveedor = await session.get(Proveedor, proveedor_id)
    if proveedor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proveedor not found")
    return proveedor


async def create_pago(session: AsyncSession, payload: PagoCreate) -> Pago:
    await _get_proveedor_or_404(session, payload.proveedor_id)
    pago = Pago(
        proveedor_id=payload.proveedor_id,
        fecha=payload.fecha,
        importe=payload.importe,
        observaciones=payload.observaciones,
    )
    session.add(pago)
    await session.flush()

    medios = [
        PagoMedio(
            pago_id=pago.id,
            tipo=item.tipo,
            importe=item.importe,
            banco=item.banco,
            numero=item.numero,
            fecha_acreditacion=item.fecha_acreditacion,
        )
        for item in payload.medios
    ]
    session.add_all(medios)
    await movimiento_cc_service.append_pago_movimiento(session, pago)
    await session.commit()
    return await get_pago(session, pago.id, with_detail=True)


async def update_pago(session: AsyncSession, pago_id: int, payload: PagoUpdate) -> Pago:
    pago = await get_pago(session, pago_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(pago, field, value)
    await session.commit()
    return await get_pago(session, pago_id, with_detail=True)


async def delete_pago(session: AsyncSession, pago_id: int) -> None:
    pago = await get_pago(session, pago_id)
    await session.delete(pago)
    await session.commit()


async def get_pago(session: AsyncSession, pago_id: int, with_detail: bool = False) -> Pago:
    if with_detail:
        stmt = (
            select(Pago)
            .options(selectinload(Pago.medios), selectinload(Pago.adjuntos))
            .where(Pago.id == pago_id)
        )
        row = (await session.execute(stmt)).unique().scalar_one_or_none()
    else:
        row = await session.get(Pago, pago_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pago not found")
    return row


async def list_pagos(session: AsyncSession, proveedor_id: int | None = None) -> list[Pago]:
    stmt = select(Pago).order_by(Pago.fecha.desc(), Pago.id.desc())
    if proveedor_id is not None:
        stmt = stmt.where(Pago.proveedor_id == proveedor_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def apply_pago(session: AsyncSession, pago_id: int, items: list[PagoAplicacionCreate]) -> list[PagoAplicacion]:
    await get_pago(session, pago_id)
    rows = []
    for item in items:
        compra = await session.get(Compra, item.compra_id)
        if compra is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Compra {item.compra_id} not found"
            )
        rows.append(PagoAplicacion(pago_id=pago_id, compra_id=item.compra_id, importe=item.importe, compra=compra))
    session.add_all(rows)
    # The trg_update_compra_saldo_pendiente trigger (on INSERT into
    # compras_pago_aplicacion) decrements Compra.saldo_pendiente and
    # recomputes estado as a side effect of this commit — do not replicate
    # that arithmetic here. See design.md D1/D2.
    await session.commit()
    for row in rows:
        await session.refresh(row, attribute_names=["compra"])
    return rows


async def list_aplicaciones_for_pago(session: AsyncSession, pago_id: int) -> list[PagoAplicacion]:
    await get_pago(session, pago_id)  # 404 if missing
    stmt = select(PagoAplicacion).where(PagoAplicacion.pago_id == pago_id).order_by(PagoAplicacion.id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_pagos_for_compra(session: AsyncSession, compra_id: int) -> list[Pago]:
    stmt = (
        select(Pago)
        .join(PagoAplicacion, PagoAplicacion.pago_id == Pago.id)
        .where(PagoAplicacion.compra_id == compra_id)
        .order_by(Pago.fecha)
    )
    result = await session.execute(stmt)
    return list(result.scalars().unique().all())


async def add_adjunto(
    session: AsyncSession,
    pago_id: int,
    filename: str,
    content: bytes,
    content_type: str | None,
) -> PagoAdjunto:
    await get_pago(session, pago_id)  # 404 if missing
    row = PagoAdjunto(pago_id=pago_id, nombre=filename, contenido=content, tipo=content_type)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def get_adjunto(session: AsyncSession, pago_id: int, adjunto_id: int) -> PagoAdjunto:
    stmt = (
        select(PagoAdjunto)
        .options(undefer(PagoAdjunto.contenido))
        .where(PagoAdjunto.id == adjunto_id, PagoAdjunto.pago_id == pago_id)
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Adjunto not found")
    return row
