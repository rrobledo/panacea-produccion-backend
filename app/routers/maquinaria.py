from datetime import date

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session
from app.schemas.maquinaria import CargaDiaRead, MaquinaRead, MaquinaWrite, ProcesoOperacionRead
from app.services import maquinaria_service as service

router = APIRouter(tags=["maquinaria"])


@router.get("/maquinas", response_model=list[MaquinaRead])
async def list_maquinas(
    tipo: str | None = None, solo_activas: bool = False, session: AsyncSession = Depends(get_session)
):
    return await service.list_maquinas(session, tipo, solo_activas)


@router.post("/maquinas", response_model=MaquinaRead, status_code=status.HTTP_201_CREATED)
async def create_maquina(payload: MaquinaWrite, session: AsyncSession = Depends(get_session)):
    return await service.crear_maquina(session, payload)


@router.get("/maquinas/{maquina_id}", response_model=MaquinaRead)
async def get_maquina(maquina_id: int, session: AsyncSession = Depends(get_session)):
    return await service.get_maquina(session, maquina_id)


@router.put("/maquinas/{maquina_id}", response_model=MaquinaRead)
async def update_maquina(maquina_id: int, payload: MaquinaWrite, session: AsyncSession = Depends(get_session)):
    maquina = await service.get_maquina(session, maquina_id)
    return await service.actualizar_maquina(session, maquina, payload)


@router.delete("/maquinas/{maquina_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_maquina(maquina_id: int, session: AsyncSession = Depends(get_session)):
    maquina = await service.get_maquina(session, maquina_id)
    await service.eliminar_maquina(session, maquina)


@router.get("/procesos/{proceso_id}/operaciones", response_model=list[ProcesoOperacionRead])
async def list_operaciones(proceso_id: int, session: AsyncSession = Depends(get_session)):
    return await service.operaciones_de_proceso(session, proceso_id)


@router.get("/carga-dia", response_model=CargaDiaRead)
async def carga_dia(fecha: date, session: AsyncSession = Depends(get_session)):
    # El tablero que hace concreto "distribuir mejor la producción diaria":
    # una fila por tipo de máquina, ordenada por uso descendente.
    return await service.carga_del_dia(session, fecha)
