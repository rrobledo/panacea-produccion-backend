from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.remitos import Remitos, RemitoDetalles
from app.schemas.remitos import RemitoCreate, RemitoUpdate

# Linear estado sequence matching panacea-mayorista-backend's
# EstadoRemito/VALID_TRANSITIONS exactly: each source estado maps to the
# single valid next estado and the timestamp field that advancing to it sets.
VALID_TRANSITIONS: dict[str, str] = {
    "creado": "en_produccion",
    "en_produccion": "preparando",
    "preparando": "listo_entregar",
    "listo_entregar": "en_entrega",
    "en_entrega": "facturado",
}

_ESTADO_TIMESTAMP_FIELD: dict[str, str] = {
    "en_produccion": "fecha_preparacion",
    "preparando": "fecha_listo",
    "listo_entregar": "fecha_despacho",
    "en_entrega": "fecha_recibido",
    "facturado": "fecha_facturacion",
}


def _add_detalle_rows(session: AsyncSession, remito_id: int, detalles) -> None:
    for item in detalles:
        if item.cantidad > 0:
            session.add(
                RemitoDetalles(
                    remito_id=remito_id,
                    producto_id=item.producto_id,
                    cantidad=item.cantidad,
                    entregado=item.entregado,
                    observaciones=item.observaciones,
                )
            )


async def create_remito(session: AsyncSession, payload: RemitoCreate) -> Remitos:
    data = payload.model_dump(exclude={"detalles"})
    remito = Remitos(fecha_carga=datetime.now(timezone.utc), **data)
    session.add(remito)
    await session.flush()
    _add_detalle_rows(session, remito.id, payload.detalles)
    await session.commit()
    return await get_remito(session, remito.id)


async def update_remito(session: AsyncSession, remito: Remitos, payload: RemitoUpdate) -> Remitos:
    # Partial update, matching mayorista's RemitoUpdate semantics — only
    # fields the caller actually set are touched.
    data = payload.model_dump(exclude={"detalles"}, exclude_unset=True)
    for field, value in data.items():
        setattr(remito, field, value)

    if payload.detalles is not None:
        await session.execute(RemitoDetalles.__table__.delete().where(RemitoDetalles.remito_id == remito.id))
        _add_detalle_rows(session, remito.id, payload.detalles)

    await session.commit()
    return await get_remito(session, remito.id)


async def transition_estado(session: AsyncSession, remito: Remitos, nuevo_estado: str) -> Remitos:
    current = remito.estado
    expected_next = VALID_TRANSITIONS.get(current)
    if expected_next is None or expected_next != nuevo_estado:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid transition: '{current}' -> '{nuevo_estado}'. Expected next state: '{expected_next}'",
        )
    setattr(remito, _ESTADO_TIMESTAMP_FIELD[nuevo_estado], datetime.now(timezone.utc))
    await session.commit()
    return await get_remito(session, remito.id)


async def get_remito(session: AsyncSession, remito_id: int) -> Remitos:
    stmt = (
        select(Remitos)
        .options(selectinload(Remitos.detalles).selectinload(RemitoDetalles.producto))
        .where(Remitos.id == remito_id)
        .execution_options(populate_existing=True)
    )
    row = (await session.execute(stmt)).unique().scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Remito not found")
    return row
