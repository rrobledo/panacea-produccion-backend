from datetime import date

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session
from app.schemas.ordenes_produccion import (
    FinalizarOrdenRequest,
    GenerarOrdenesRequest,
    OrdenProduccionRead,
    PreviewOrdenesResponse,
)
from app.services import ordenes_produccion_service as service

router = APIRouter(prefix="/ordenes-produccion", tags=["ordenes-produccion"])


@router.get("", response_model=list[OrdenProduccionRead])
async def list_ordenes(
    fecha_fabricacion: date | None = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    estado: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    ordenes = await service.list_ordenes(
        session, fecha_fabricacion=fecha_fabricacion, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta, estado=estado
    )
    return [OrdenProduccionRead.from_orm_row(o) for o in ordenes]


def _overrides(payload: GenerarOrdenesRequest) -> dict[int, int] | None:
    if payload.cantidades is None:
        return None
    return {c.programacion_id: c.cantidad for c in payload.cantidades}


@router.post("/preview", response_model=PreviewOrdenesResponse)
async def preview_ordenes(payload: GenerarOrdenesRequest, session: AsyncSession = Depends(get_session)):
    """Calcula las órdenes pendientes de esa fecha, sin persistir nada."""
    ordenes, existentes = await service.preview_ordenes(session, payload.fecha, _overrides(payload))
    return {"ordenes": ordenes, "ordenes_existentes": existentes}


@router.post("/generar", response_model=list[OrdenProduccionRead], status_code=status.HTTP_201_CREATED)
async def generar_ordenes(payload: GenerarOrdenesRequest, session: AsyncSession = Depends(get_session)):
    ordenes = await service.generar_ordenes(session, payload.fecha, _overrides(payload))
    return [OrdenProduccionRead.from_orm_row(o) for o in ordenes]


@router.get("/{orden_id}", response_model=OrdenProduccionRead)
async def get_orden(orden_id: int, session: AsyncSession = Depends(get_session)):
    orden = await service.get_orden(session, orden_id)
    return OrdenProduccionRead.from_orm_row(orden)


@router.delete("/{orden_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_orden(orden_id: int, session: AsyncSession = Depends(get_session)):
    orden = await service.get_orden(session, orden_id)
    await service.eliminar_orden(session, orden)


@router.post("/{orden_id}/iniciar", response_model=OrdenProduccionRead)
async def iniciar_produccion(orden_id: int, session: AsyncSession = Depends(get_session)):
    orden = await service.get_orden(session, orden_id)
    orden = await service.iniciar_produccion(session, orden)
    return OrdenProduccionRead.from_orm_row(orden)


@router.post("/{orden_id}/cancelar", response_model=OrdenProduccionRead)
async def cancelar_orden(orden_id: int, session: AsyncSession = Depends(get_session)):
    orden = await service.get_orden(session, orden_id)
    orden = await service.cancelar_orden(session, orden)
    return OrdenProduccionRead.from_orm_row(orden)


@router.post("/{orden_id}/finalizar", response_model=OrdenProduccionRead)
async def finalizar_orden(orden_id: int, payload: FinalizarOrdenRequest, session: AsyncSession = Depends(get_session)):
    orden = await service.get_orden(session, orden_id)
    orden = await service.finalizar_orden(session, orden, payload)
    return OrdenProduccionRead.from_orm_row(orden)
