from datetime import date

from fastapi import APIRouter, Depends, File, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, require_api_key
from app.schemas.compra import (
    CompraAdjuntoRead,
    CompraCreate,
    CompraDetailRead,
    CompraDetalleCreate,
    CompraImpuestoCreate,
    CompraRead,
    CompraUpdate,
)
from app.schemas.pago import PagoRead
from app.services import compra_service as service
from app.services import pago_service

router = APIRouter(prefix="/compras", tags=["compras"])


@router.get("", response_model=list[CompraRead])
async def list_compras(
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    estado: str | None = None,
    proveedor_id: int | None = None,
    con_saldo: bool | None = None,
    session: AsyncSession = Depends(get_session),
):
    return await service.list_compras(session, fecha_desde, fecha_hasta, estado, proveedor_id, con_saldo)


@router.post(
    "",
    response_model=CompraDetailRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_api_key)],
)
async def create_compra(payload: CompraCreate, session: AsyncSession = Depends(get_session)):
    return await service.create_compra(session, payload)


@router.get("/{compra_id}", response_model=CompraDetailRead)
async def get_compra(compra_id: int, session: AsyncSession = Depends(get_session)):
    return await service.get_compra(session, compra_id, with_detail=True)


@router.put("/{compra_id}", response_model=CompraDetailRead, dependencies=[Depends(require_api_key)])
async def update_compra(compra_id: int, payload: CompraUpdate, session: AsyncSession = Depends(get_session)):
    return await service.update_compra(session, compra_id, payload)


@router.delete("/{compra_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_api_key)])
async def delete_compra(compra_id: int, session: AsyncSession = Depends(get_session)):
    await service.delete_compra(session, compra_id)


@router.post(
    "/{compra_id}/detalle",
    response_model=CompraDetailRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_api_key)],
)
async def add_detalle(
    compra_id: int,
    payload: CompraDetalleCreate | list[CompraDetalleCreate],
    session: AsyncSession = Depends(get_session),
):
    items = payload if isinstance(payload, list) else [payload]
    return await service.add_detalle(session, compra_id, items)


@router.post(
    "/{compra_id}/impuestos",
    response_model=CompraDetailRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_api_key)],
)
async def add_impuestos(
    compra_id: int,
    payload: CompraImpuestoCreate | list[CompraImpuestoCreate],
    session: AsyncSession = Depends(get_session),
):
    items = payload if isinstance(payload, list) else [payload]
    return await service.add_impuestos(session, compra_id, items)


@router.post(
    "/{compra_id}/adjuntos",
    response_model=CompraAdjuntoRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_api_key)],
)
async def upload_adjunto(
    compra_id: int,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
):
    content = await file.read()
    return await service.add_adjunto(session, compra_id, file.filename, content, file.content_type)


@router.get("/{compra_id}/adjuntos/{adjunto_id}")
async def download_adjunto(compra_id: int, adjunto_id: int, session: AsyncSession = Depends(get_session)):
    adjunto = await service.get_adjunto(session, compra_id, adjunto_id)
    return Response(
        content=adjunto.contenido,
        media_type=adjunto.tipo or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{adjunto.nombre}"'},
    )


@router.get("/{compra_id}/pagos", response_model=list[PagoRead])
async def list_pagos_for_compra(compra_id: int, session: AsyncSession = Depends(get_session)):
    await service.get_compra(session, compra_id)
    return await pago_service.list_pagos_for_compra(session, compra_id)
