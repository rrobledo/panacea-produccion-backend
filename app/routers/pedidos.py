from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session
from app.schemas.pedido import (
    EstadoTransitionRequest,
    PedidoCreate,
    PedidoEntregaRequest,
    PedidoRead,
    PedidoUpdate,
)
from app.services import pedido_service as service

router = APIRouter(prefix="/pedidos", tags=["pedidos"])


@router.get("", response_model=list[PedidoRead])
async def list_pedidos(
    tipo: str | None = None,
    cliente_id: int | None = None,
    sucursal_id: int | None = None,
    estado: str | None = None,
    fecha_desde: datetime | None = Query(None, description="Filter by fecha_entrega >= fecha_desde"),
    fecha_hasta: datetime | None = Query(None, description="Filter by fecha_entrega <= fecha_hasta"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
):
    pedidos = await service.list_pedidos(
        session,
        tipo=tipo,
        cliente_id=cliente_id,
        sucursal_id=sucursal_id,
        estado=estado,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        skip=skip,
        limit=limit,
    )
    return [PedidoRead.from_orm_row(row) for row in pedidos]


@router.post("", response_model=PedidoRead, status_code=status.HTTP_201_CREATED)
async def create_pedido(payload: PedidoCreate, session: AsyncSession = Depends(get_session)):
    pedido = await service.create_pedido(session, payload)
    return PedidoRead.from_orm_row(pedido)


@router.get("/{pedido_id}", response_model=PedidoRead)
async def get_pedido(pedido_id: int, session: AsyncSession = Depends(get_session)):
    pedido = await service.get_pedido(session, pedido_id)
    return PedidoRead.from_orm_row(pedido)


@router.patch("/{pedido_id}/estado", response_model=PedidoRead)
async def transition_estado(
    pedido_id: int, payload: EstadoTransitionRequest, session: AsyncSession = Depends(get_session)
):
    pedido = await service.get_pedido(session, pedido_id)
    pedido = await service.transition_estado(session, pedido, payload.nuevo_estado)
    return PedidoRead.from_orm_row(pedido)


@router.patch("/{pedido_id}/entrega", response_model=PedidoRead)
async def registrar_entrega(
    pedido_id: int, payload: PedidoEntregaRequest, session: AsyncSession = Depends(get_session)
):
    pedido = await service.get_pedido(session, pedido_id)
    pedido = await service.registrar_entrega(session, pedido, payload)
    return PedidoRead.from_orm_row(pedido)


@router.put("/{pedido_id}", response_model=PedidoRead)
async def update_pedido(pedido_id: int, payload: PedidoUpdate, session: AsyncSession = Depends(get_session)):
    pedido = await service.get_pedido(session, pedido_id)
    service.ensure_pendiente(pedido)
    pedido = await service.update_pedido(session, pedido, payload)
    return PedidoRead.from_orm_row(pedido)


@router.delete("/{pedido_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pedido(pedido_id: int, session: AsyncSession = Depends(get_session)):
    pedido = await service.get_pedido(session, pedido_id)
    service.ensure_pendiente(pedido)
    await session.delete(pedido)
    await session.commit()
