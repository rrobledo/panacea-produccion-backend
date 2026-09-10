from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session
from app.models.centro_trabajo import CentroTrabajo
from app.schemas.costeo_grafo import (
    CentroTrabajoRead,
    CentroTrabajoWrite,
    CostoArticuloRead,
    DesvioMermaRead,
)
from app.services import costeo_grafo_service, desvio_merma_service

router = APIRouter(tags=["costeo-grafo"])


@router.get("/centros-trabajo", response_model=list[CentroTrabajoRead])
async def list_centros(session: AsyncSession = Depends(get_session)):
    return list(
        (await session.execute(select(CentroTrabajo).order_by(CentroTrabajo.nombre))).scalars().all()
    )


@router.post("/centros-trabajo", response_model=CentroTrabajoRead, status_code=status.HTTP_201_CREATED)
async def create_centro(payload: CentroTrabajoWrite, session: AsyncSession = Depends(get_session)):
    existente = (
        await session.execute(select(CentroTrabajo).where(CentroTrabajo.nombre == payload.nombre))
    ).scalars().first()
    if existente is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Ya existe un centro de trabajo llamado '{payload.nombre}'",
        )
    centro = CentroTrabajo(**payload.model_dump())
    session.add(centro)
    await session.commit()
    await session.refresh(centro)
    return centro


@router.put("/centros-trabajo/{centro_id}", response_model=CentroTrabajoRead)
async def update_centro(
    centro_id: int, payload: CentroTrabajoWrite, session: AsyncSession = Depends(get_session)
):
    centro = (
        await session.execute(select(CentroTrabajo).where(CentroTrabajo.id == centro_id))
    ).scalars().first()
    if centro is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Centro de trabajo no encontrado")
    for campo, valor in payload.model_dump().items():
        setattr(centro, campo, valor)
    await session.commit()
    await session.refresh(centro)
    return centro


@router.get("/costeo-grafo", response_model=list[CostoArticuloRead])
async def costeo_de_todos(session: AsyncSession = Depends(get_session)):
    return [CostoArticuloRead.from_costo(c) for c in await costeo_grafo_service.costo_de_todos(session)]


@router.get("/costeo-grafo/{articulo_id}", response_model=CostoArticuloRead)
async def costeo_de_articulo(articulo_id: int, session: AsyncSession = Depends(get_session)):
    # El costo por capas: el semielaborado entra ya calculado, no aplanado a
    # insumos, así que cambiar el precio de la harina recostea solo todo lo que
    # consume esa masa.
    return CostoArticuloRead.from_costo(await costeo_grafo_service.costo_de_articulo(session, articulo_id))


@router.get("/desvio-merma", response_model=list[DesvioMermaRead])
async def desvio_merma(
    fecha_desde: date | None = None, fecha_hasta: date | None = None,
    session: AsyncSession = Depends(get_session),
):
    return await desvio_merma_service.desvios(session, fecha_desde, fecha_hasta)
