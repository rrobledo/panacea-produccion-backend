from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session
from app.schemas.remito import EstadoTransitionRequest, RemitoCreate, RemitoRead, RemitoUpdate
from app.services import remito_service as service

router = APIRouter(prefix="/remitos", tags=["remitos"])


@router.get("", response_model=list[RemitoRead])
async def list_remitos(
    tipo: str | None = None,
    cliente_id: int | None = None,
    pedido_id: int | None = None,
    origen_sucursal_id: int | None = None,
    destino_sucursal_id: int | None = None,
    estado: str | None = None,
    fecha_desde: datetime | None = Query(None, description="Filter by fecha_carga >= fecha_desde"),
    fecha_hasta: datetime | None = Query(None, description="Filter by fecha_carga <= fecha_hasta"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
):
    remitos = await service.list_remitos(
        session,
        tipo=tipo,
        cliente_id=cliente_id,
        pedido_id=pedido_id,
        origen_sucursal_id=origen_sucursal_id,
        destino_sucursal_id=destino_sucursal_id,
        estado=estado,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        skip=skip,
        limit=limit,
    )
    return [RemitoRead.from_orm_row(row) for row in remitos]


@router.post("", response_model=RemitoRead, status_code=status.HTTP_201_CREATED)
async def create_remito(payload: RemitoCreate, session: AsyncSession = Depends(get_session)):
    remito = await service.create_remito(session, payload)
    return RemitoRead.from_orm_row(remito)


@router.get("/{remito_id}", response_model=RemitoRead)
async def get_remito(remito_id: int, session: AsyncSession = Depends(get_session)):
    remito = await service.get_remito(session, remito_id)
    return RemitoRead.from_orm_row(remito)


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
    service.ensure_editable(remito)
    remito = await service.update_remito(session, remito, payload)
    return RemitoRead.from_orm_row(remito)


@router.delete("/{remito_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_remito(remito_id: int, session: AsyncSession = Depends(get_session)):
    remito = await service.get_remito(session, remito_id)
    service.ensure_editable(remito)
    await session.delete(remito)
    await session.commit()
