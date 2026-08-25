from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.remito import Remito, RemitoDetalle
from app.schemas.remito import RemitoCreate, RemitoUpdate
from app.schemas.vocab import REMITO_ESTADO_TIMESTAMP_FIELD, REMITO_VALID_TRANSITIONS


def _remito_stmt():
    return select(Remito).options(
        selectinload(Remito.detalles).selectinload(RemitoDetalle.producto),
        selectinload(Remito.origen_sucursal),
        selectinload(Remito.destino_sucursal),
    )


def _add_detalle_rows(session: AsyncSession, remito_id: int, detalles) -> None:
    for item in detalles:
        if item.cantidad > 0:
            session.add(
                RemitoDetalle(
                    remito_id=remito_id,
                    producto_id=item.producto_id,
                    cantidad=item.cantidad,
                    observaciones=item.observaciones,
                )
            )


async def create_remito(session: AsyncSession, payload: RemitoCreate) -> Remito:
    data = payload.model_dump(exclude={"detalles"})
    now = datetime.now(timezone.utc)
    remito = Remito(fecha_carga=now, fecha_listo=now, **data)
    session.add(remito)
    await session.flush()
    _add_detalle_rows(session, remito.id, payload.detalles)
    await session.commit()
    return await get_remito(session, remito.id)


async def list_remitos(
    session: AsyncSession,
    tipo: str | None = None,
    cliente_id: int | None = None,
    pedido_id: int | None = None,
    origen_sucursal_id: int | None = None,
    destino_sucursal_id: int | None = None,
    estado: str | None = None,
    fecha_desde: datetime | None = None,
    fecha_hasta: datetime | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[Remito]:
    stmt = _remito_stmt()
    if tipo is not None:
        stmt = stmt.where(Remito.tipo == tipo)
    if cliente_id is not None:
        stmt = stmt.where(Remito.cliente_id == cliente_id)
    if pedido_id is not None:
        stmt = stmt.where(Remito.pedido_id == pedido_id)
    if origen_sucursal_id is not None:
        stmt = stmt.where(Remito.origen_sucursal_id == origen_sucursal_id)
    if destino_sucursal_id is not None:
        stmt = stmt.where(Remito.destino_sucursal_id == destino_sucursal_id)
    if fecha_desde:
        stmt = stmt.where(Remito.fecha_carga >= fecha_desde)
    if fecha_hasta:
        stmt = stmt.where(Remito.fecha_carga <= fecha_hasta)
    stmt = stmt.order_by(Remito.fecha_carga.desc()).offset(skip).limit(limit)
    result = await session.execute(stmt)
    rows = list(result.unique().scalars().all())
    if estado is not None:
        rows = [r for r in rows if r.estado == estado]
    return rows


async def get_remito(session: AsyncSession, remito_id: int) -> Remito:
    stmt = _remito_stmt().where(Remito.id == remito_id).execution_options(populate_existing=True)
    row = (await session.execute(stmt)).unique().scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Remito not found")
    return row


def ensure_editable(remito: Remito) -> None:
    if remito.estado != "LISTO":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only remitos in 'LISTO' estado can be edited or deleted",
        )


async def update_remito(session: AsyncSession, remito: Remito, payload: RemitoUpdate) -> Remito:
    data = payload.model_dump(exclude={"detalles"}, exclude_unset=True)
    for field, value in data.items():
        setattr(remito, field, value)

    if payload.detalles is not None:
        # Merge by producto_id instead of delete-and-recreate, so
        # fecha_creacion is preserved on items that already existed — it
        # only advances for genuinely new lines. See RemitoDetalle.fecha_creacion.
        existentes = {d.producto_id: d for d in remito.detalles}
        vistos: set[int] = set()
        for item in payload.detalles:
            if item.cantidad <= 0:
                continue
            vistos.add(item.producto_id)
            detalle = existentes.get(item.producto_id)
            if detalle is not None:
                detalle.cantidad = item.cantidad
                detalle.observaciones = item.observaciones
            else:
                session.add(
                    RemitoDetalle(
                        remito_id=remito.id,
                        producto_id=item.producto_id,
                        cantidad=item.cantidad,
                        observaciones=item.observaciones,
                    )
                )
        for producto_id, detalle in existentes.items():
            if producto_id not in vistos:
                await session.delete(detalle)

    await session.commit()
    return await get_remito(session, remito.id)


async def transition_estado(session: AsyncSession, remito: Remito, nuevo_estado: str) -> Remito:
    current = remito.estado
    expected_next = REMITO_VALID_TRANSITIONS.get(current)
    if expected_next is None or expected_next != nuevo_estado:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid transition: '{current}' -> '{nuevo_estado}'. Expected next state: '{expected_next}'",
        )
    setattr(remito, REMITO_ESTADO_TIMESTAMP_FIELD[nuevo_estado], datetime.now(timezone.utc))
    await session.commit()
    return await get_remito(session, remito.id)
