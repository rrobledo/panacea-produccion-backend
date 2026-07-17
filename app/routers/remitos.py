from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.deps import get_session
from app.models.remitos import RemitoDetalles, Remitos
from app.schemas.remitos import EstadoTransitionRequest, RemitoCreate, RemitoRead, RemitoUpdate
from app.services import remitos_service as service

router = APIRouter(prefix="/remitos", tags=["remitos"])

# Mirrors Remitos.estado's precedence exactly, as SQL conditions, so
# filtering doesn't require loading every row into Python. Labels match the
# entity's own `estado` values (unlike panacea-mayorista-backend's `status`
# filter, whose EstadoRemitoFilter labels are shifted by one step from what
# its own derive_estado() would call the same condition).
_ESTADO_CONDITIONS = {
    "creado": lambda: and_(
        Remitos.fecha_preparacion.is_(None),
        Remitos.fecha_listo.is_(None),
        Remitos.fecha_despacho.is_(None),
        Remitos.fecha_recibido.is_(None),
        Remitos.fecha_facturacion.is_(None),
    ),
    "en_produccion": lambda: and_(
        Remitos.fecha_preparacion.isnot(None),
        Remitos.fecha_listo.is_(None),
        Remitos.fecha_despacho.is_(None),
        Remitos.fecha_recibido.is_(None),
        Remitos.fecha_facturacion.is_(None),
    ),
    "preparando": lambda: and_(
        Remitos.fecha_listo.isnot(None),
        Remitos.fecha_despacho.is_(None),
        Remitos.fecha_recibido.is_(None),
        Remitos.fecha_facturacion.is_(None),
    ),
    "listo_entregar": lambda: and_(
        Remitos.fecha_despacho.isnot(None),
        Remitos.fecha_recibido.is_(None),
        Remitos.fecha_facturacion.is_(None),
    ),
    "en_entrega": lambda: and_(Remitos.fecha_recibido.isnot(None), Remitos.fecha_facturacion.is_(None)),
    "facturado": lambda: Remitos.fecha_facturacion.isnot(None),
}


def _remitos_stmt():
    return select(Remitos).options(selectinload(Remitos.detalles).selectinload(RemitoDetalles.producto))


@router.get("", response_model=list[RemitoRead])
async def list_remitos(
    cliente_id: int | None = None,
    status: str | None = None,
    fecha_desde: datetime | None = Query(None, description="Filter by fecha_entrega >= fecha_desde"),
    fecha_hasta: datetime | None = Query(None, description="Filter by fecha_entrega <= fecha_hasta"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
):
    stmt = _remitos_stmt()
    if cliente_id is not None:
        stmt = stmt.where(Remitos.cliente_id == cliente_id)
    if fecha_desde:
        stmt = stmt.where(Remitos.fecha_entrega >= fecha_desde)
    if fecha_hasta:
        stmt = stmt.where(Remitos.fecha_entrega <= fecha_hasta)
    if status is not None and status in _ESTADO_CONDITIONS:
        stmt = stmt.where(_ESTADO_CONDITIONS[status]())
    stmt = stmt.order_by(Remitos.fecha_carga.desc()).offset(skip).limit(limit)
    result = await session.execute(stmt)
    return [RemitoRead.from_orm_row(row) for row in result.unique().scalars().all()]


@router.post("", response_model=RemitoRead, status_code=status.HTTP_201_CREATED)
async def create_remito(payload: RemitoCreate, session: AsyncSession = Depends(get_session)):
    remito = await service.create_remito(session, payload)
    return RemitoRead.from_orm_row(remito)


@router.get("/{remito_id}", response_model=RemitoRead)
async def get_remito(remito_id: int, session: AsyncSession = Depends(get_session)):
    remito = await service.get_remito(session, remito_id)
    return RemitoRead.from_orm_row(remito)


def _ensure_creado(remito: Remitos) -> None:
    if remito.estado != "creado":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only remitos in 'creado' estado can be edited or deleted",
        )


@router.patch("/{remito_id}/estado", response_model=RemitoRead)
async def transition_estado(
    remito_id: int, payload: EstadoTransitionRequest, session: AsyncSession = Depends(get_session)
):
    remito = await service.get_remito(session, remito_id)
    remito = await service.transition_estado(session, remito, payload.nuevo_estado)
    return RemitoRead.from_orm_row(remito)


@router.put("/{remito_id}", response_model=RemitoRead)
async def update_remito(remito_id: int, payload: RemitoUpdate, session: AsyncSession = Depends(get_session)):
    remito = await service.get_remito(session, remito_id)
    _ensure_creado(remito)
    remito = await service.update_remito(session, remito, payload)
    return RemitoRead.from_orm_row(remito)


@router.delete("/{remito_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_remito(remito_id: int, session: AsyncSession = Depends(get_session)):
    remito = await service.get_remito(session, remito_id)
    _ensure_creado(remito)
    await session.delete(remito)
    await session.commit()
