from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.compra import CompraDetalle
from app.models.orden_compra import OrdenCompra, OrdenCompraDetalle
from app.models.proveedor import Proveedor
from app.schemas.orden_compra import OrdenCompraCreate, OrdenCompraUpdate


async def _get_proveedor_or_404(session: AsyncSession, proveedor_id: int) -> Proveedor:
    proveedor = await session.get(Proveedor, proveedor_id)
    if proveedor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proveedor not found")
    return proveedor


async def create_orden_compra(session: AsyncSession, payload: OrdenCompraCreate) -> OrdenCompra:
    await _get_proveedor_or_404(session, payload.proveedor_id)
    orden = OrdenCompra(
        proveedor_id=payload.proveedor_id,
        fecha=payload.fecha,
        fecha_entrega_estimada=payload.fecha_entrega_estimada,
        observaciones=payload.observaciones,
    )
    session.add(orden)
    await session.flush()

    detalle_rows = [
        OrdenCompraDetalle(
            orden_compra_id=orden.id,
            descripcion=item.descripcion,
            insumo_id=item.insumo_id,
            cantidad_pedida=item.cantidad_pedida,
            precio_unitario_estimado=item.precio_unitario_estimado,
        )
        for item in payload.detalle
    ]
    session.add_all(detalle_rows)
    await session.commit()
    return await get_orden_compra(session, orden.id, with_detail=True)


async def update_orden_compra(session: AsyncSession, orden_id: int, payload: OrdenCompraUpdate) -> OrdenCompra:
    orden = await get_orden_compra(session, orden_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(orden, field, value)
    await session.commit()
    return await get_orden_compra(session, orden_id, with_detail=True)


async def delete_orden_compra(session: AsyncSession, orden_id: int) -> None:
    orden = await get_orden_compra(session, orden_id)
    await session.delete(orden)
    await session.commit()


async def get_orden_compra(session: AsyncSession, orden_id: int, with_detail: bool = False) -> OrdenCompra:
    if with_detail:
        stmt = (
            select(OrdenCompra)
            .options(selectinload(OrdenCompra.detalle))
            .where(OrdenCompra.id == orden_id)
            .execution_options(populate_existing=True)
        )
        row = (await session.execute(stmt)).unique().scalar_one_or_none()
    else:
        row = await session.get(OrdenCompra, orden_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OrdenCompra not found")
    return row


async def list_ordenes_compra(
    session: AsyncSession, proveedor_id: int | None = None, estado: str | None = None
) -> list[OrdenCompra]:
    stmt = select(OrdenCompra).order_by(OrdenCompra.fecha)
    if proveedor_id is not None:
        stmt = stmt.where(OrdenCompra.proveedor_id == proveedor_id)
    if estado is not None:
        stmt = stmt.where(OrdenCompra.estado == estado)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def register_reception(
    session: AsyncSession, orden_compra_id: int, compra_detalle: list[CompraDetalle]
) -> None:
    """Increment cantidad_recibida on OrdenCompraDetalle rows matched by
    descripcion and advance OrdenCompra.estado, when a Compra references
    orden_compra_id (design.md D8).

    Matching by descripcion (case-insensitive) is the simplest strategy
    that needs no shared identifier between CompraDetalle and
    OrdenCompraDetalle; unmatched compra detalle rows are skipped. No
    over-delivery tolerance or unit-conversion logic — consistent with
    this change's "no separate goods-receipt module" non-goal.
    """
    orden = await get_orden_compra(session, orden_compra_id, with_detail=True)
    by_descripcion = {(d.descripcion or "").strip().lower(): d for d in orden.detalle}

    for item in compra_detalle:
        oc_detalle = by_descripcion.get(item.descripcion.strip().lower())
        if oc_detalle is not None:
            oc_detalle.cantidad_recibida += item.cantidad

    total_pedida = sum(d.cantidad_pedida for d in orden.detalle)
    total_recibida = sum(d.cantidad_recibida for d in orden.detalle)
    if total_recibida <= 0:
        orden.estado = "PENDIENTE"
    elif total_recibida >= total_pedida:
        orden.estado = "RECIBIDA"
    else:
        orden.estado = "PARCIAL"
