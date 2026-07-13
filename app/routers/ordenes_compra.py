from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, require_api_key
from app.schemas.orden_compra import (
    OrdenCompraCreate,
    OrdenCompraDetailRead,
    OrdenCompraRead,
    OrdenCompraUpdate,
)
from app.services import orden_compra_service as service

router = APIRouter(prefix="/ordenes-compra", tags=["ordenes-compra"])


@router.get("", response_model=list[OrdenCompraRead])
async def list_ordenes_compra(
    proveedor_id: int | None = None,
    estado: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    return await service.list_ordenes_compra(session, proveedor_id, estado)


@router.post(
    "",
    response_model=OrdenCompraDetailRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_api_key)],
)
async def create_orden_compra(payload: OrdenCompraCreate, session: AsyncSession = Depends(get_session)):
    return await service.create_orden_compra(session, payload)


@router.get("/{orden_id}", response_model=OrdenCompraDetailRead)
async def get_orden_compra(orden_id: int, session: AsyncSession = Depends(get_session)):
    return await service.get_orden_compra(session, orden_id, with_detail=True)


@router.put("/{orden_id}", response_model=OrdenCompraDetailRead, dependencies=[Depends(require_api_key)])
async def update_orden_compra(
    orden_id: int, payload: OrdenCompraUpdate, session: AsyncSession = Depends(get_session)
):
    return await service.update_orden_compra(session, orden_id, payload)


@router.delete("/{orden_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_api_key)])
async def delete_orden_compra(orden_id: int, session: AsyncSession = Depends(get_session)):
    await service.delete_orden_compra(session, orden_id)
