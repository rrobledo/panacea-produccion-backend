from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.remitos import Remitos, RemitoDetalles
from app.schemas.remitos import RemitoCreate


def _add_detalle_rows(session: AsyncSession, remito_id: int, productos) -> None:
    for item in productos:
        if item.cantidad > 0:
            session.add(
                RemitoDetalles(
                    remito_id=remito_id,
                    producto_id=item.producto,
                    cantidad=item.cantidad,
                    entregado=item.entregado,
                    observaciones=item.observaciones,
                )
            )


async def create_remito(session: AsyncSession, payload: RemitoCreate) -> Remitos:
    data = payload.model_dump(exclude={"productos", "cliente"})
    remito = Remitos(cliente_id=payload.cliente, fecha_carga=datetime.now(timezone.utc), **data)
    session.add(remito)
    await session.flush()
    _add_detalle_rows(session, remito.id, payload.productos)
    await session.commit()
    return await get_remito(session, remito.id)


async def update_remito(session: AsyncSession, remito: Remitos, payload: RemitoCreate) -> Remitos:
    data = payload.model_dump(exclude={"productos", "cliente"})
    for field, value in data.items():
        setattr(remito, field, value)
    remito.cliente_id = payload.cliente
    remito.fecha_carga = datetime.now(timezone.utc)

    # The reference RemitosSerializer.update() is a no-op stub (computes a
    # diff and discards it) — not replicated. Instead: full replace of the
    # detail lines, same cantidad<=0 exclusion as create.
    await session.execute(RemitoDetalles.__table__.delete().where(RemitoDetalles.remito_id == remito.id))
    _add_detalle_rows(session, remito.id, payload.productos)

    await session.commit()
    return await get_remito(session, remito.id)


async def get_remito(session: AsyncSession, remito_id: int) -> Remitos:
    stmt = (
        select(Remitos)
        .options(selectinload(Remitos.productos).selectinload(RemitoDetalles.producto))
        .where(Remitos.id == remito_id)
        .execution_options(populate_existing=True)
    )
    row = (await session.execute(stmt)).unique().scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Remito not found")
    return row
