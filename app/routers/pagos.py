from datetime import date

from fastapi import APIRouter, Depends, File, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session
from app.schemas.pago import (
    PagoAdjuntoRead,
    PagoAplicacionCreate,
    PagoAplicacionRead,
    PagoCreate,
    PagoDetailRead,
    PagoRead,
    PagoUpdate,
)
from app.services import pago_service as service

router = APIRouter(prefix="/pagos", tags=["pagos"])


@router.get("", response_model=list[PagoRead])
async def list_pagos(
    proveedor_id: int | None = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    session: AsyncSession = Depends(get_session),
):
    return await service.list_pagos(session, proveedor_id, fecha_desde, fecha_hasta)


@router.post(
    "",
    response_model=PagoDetailRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_pago(payload: PagoCreate, session: AsyncSession = Depends(get_session)):
    return await service.create_pago(session, payload)


@router.get("/{pago_id}", response_model=PagoDetailRead)
async def get_pago(pago_id: int, session: AsyncSession = Depends(get_session)):
    return await service.get_pago(session, pago_id, with_detail=True)


@router.put("/{pago_id}", response_model=PagoDetailRead)
async def update_pago(pago_id: int, payload: PagoUpdate, session: AsyncSession = Depends(get_session)):
    return await service.update_pago(session, pago_id, payload)


@router.delete("/{pago_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pago(pago_id: int, session: AsyncSession = Depends(get_session)):
    await service.delete_pago(session, pago_id)


@router.post(
    "/{pago_id}/aplicaciones",
    response_model=list[PagoAplicacionRead],
    status_code=status.HTTP_201_CREATED,
)
async def apply_pago(
    pago_id: int,
    payload: PagoAplicacionCreate | list[PagoAplicacionCreate],
    session: AsyncSession = Depends(get_session),
):
    items = payload if isinstance(payload, list) else [payload]
    return await service.apply_pago(session, pago_id, items)


@router.get("/{pago_id}/aplicaciones", response_model=list[PagoAplicacionRead])
async def list_aplicaciones(pago_id: int, session: AsyncSession = Depends(get_session)):
    return await service.list_aplicaciones_for_pago(session, pago_id)


@router.post(
    "/{pago_id}/adjuntos",
    response_model=PagoAdjuntoRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_adjunto(
    pago_id: int,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
):
    content = await file.read()
    return await service.add_adjunto(session, pago_id, file.filename, content, file.content_type)


@router.get("/{pago_id}/adjuntos/{adjunto_id}")
async def download_adjunto(pago_id: int, adjunto_id: int, session: AsyncSession = Depends(get_session)):
    adjunto = await service.get_adjunto(session, pago_id, adjunto_id)
    return Response(
        content=adjunto.contenido,
        media_type=adjunto.tipo or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{adjunto.nombre}"'},
    )
