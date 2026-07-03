from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.deps import get_session, require_api_key
from app.models.clientes import Clientes
from app.models.remitos import RemitoDetalles, Remitos
from app.schemas.remitos import RemitoCreate, RemitoRead
from app.services import remitos_service as service

router = APIRouter(prefix="/remitos", tags=["remitos"])

# Mirrors the Remitos.estado property's precedence exactly, as SQL
# conditions, so filtering doesn't require loading every row into Python.
_ESTADO_CONDITIONS = {
    "ENTREGADO": lambda: Remitos.fecha_recibido.isnot(None),
    "EN CAMINO": lambda: and_(Remitos.fecha_recibido.is_(None), Remitos.fecha_despacho.isnot(None)),
    "PREPARADO": lambda: and_(
        Remitos.fecha_recibido.is_(None), Remitos.fecha_despacho.is_(None), Remitos.fecha_listo.isnot(None)
    ),
    "EN_PREPARACION": lambda: and_(
        Remitos.fecha_recibido.is_(None),
        Remitos.fecha_despacho.is_(None),
        Remitos.fecha_listo.is_(None),
        Remitos.fecha_preparacion.isnot(None),
    ),
    "PENDIENTE": lambda: and_(
        Remitos.fecha_recibido.is_(None),
        Remitos.fecha_despacho.is_(None),
        Remitos.fecha_listo.is_(None),
        Remitos.fecha_preparacion.is_(None),
    ),
}


@router.get("", response_model=list[RemitoRead])
async def list_remitos(
    cliente: str | None = None,
    estado: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    stmt = (
        select(Remitos)
        .options(selectinload(Remitos.productos).selectinload(RemitoDetalles.producto))
        .order_by(Remitos.fecha_entrega)
    )
    if cliente:
        pattern = f"%{cliente}%"
        stmt = stmt.join(Clientes).where(or_(Clientes.nom1.ilike(pattern), Clientes.nom2.ilike(pattern)))
    if estado is not None and estado != "ALL" and estado in _ESTADO_CONDITIONS:
        stmt = stmt.where(_ESTADO_CONDITIONS[estado]())
    result = await session.execute(stmt)
    return [RemitoRead.from_orm_row(row) for row in result.unique().scalars().all()]


@router.post("", response_model=RemitoRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_api_key)])
async def create_remito(payload: RemitoCreate, session: AsyncSession = Depends(get_session)):
    remito = await service.create_remito(session, payload)
    return RemitoRead.from_orm_row(remito)


@router.get("/{remito_id}", response_model=RemitoRead)
async def get_remito(remito_id: int, session: AsyncSession = Depends(get_session)):
    remito = await service.get_remito(session, remito_id)
    return RemitoRead.from_orm_row(remito)


@router.put("/{remito_id}", response_model=RemitoRead, dependencies=[Depends(require_api_key)])
async def update_remito(remito_id: int, payload: RemitoCreate, session: AsyncSession = Depends(get_session)):
    remito = await service.get_remito(session, remito_id)
    remito = await service.update_remito(session, remito, payload)
    return RemitoRead.from_orm_row(remito)


@router.delete("/{remito_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_api_key)])
async def delete_remito(remito_id: int, session: AsyncSession = Depends(get_session)):
    remito = await service.get_remito(session, remito_id)
    await session.delete(remito)
    await session.commit()
