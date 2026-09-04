from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session
from app.schemas.ubicacion import UbicacionCreate, UbicacionRead, UbicacionUpdate
from app.services import ubicacion_service as service

router = APIRouter(prefix="/ubicaciones", tags=["ubicaciones"])


@router.get("", response_model=list[UbicacionRead])
async def list_ubicaciones(
    nombre: str | None = None, q: str | None = None, session: AsyncSession = Depends(get_session)
):
    return await service.list_ubicaciones(session, nombre or q)


@router.post("", response_model=UbicacionRead, status_code=status.HTTP_201_CREATED)
async def create_ubicacion(payload: UbicacionCreate, session: AsyncSession = Depends(get_session)):
    return await service.create_ubicacion(session, payload)


@router.get("/{ubicacion_id}", response_model=UbicacionRead)
async def get_ubicacion(ubicacion_id: int, session: AsyncSession = Depends(get_session)):
    return await service.get_ubicacion(session, ubicacion_id)


@router.put("/{ubicacion_id}", response_model=UbicacionRead)
async def update_ubicacion(ubicacion_id: int, payload: UbicacionUpdate, session: AsyncSession = Depends(get_session)):
    ubicacion = await service.get_ubicacion(session, ubicacion_id)
    return await service.update_ubicacion(session, ubicacion, payload)


@router.delete("/{ubicacion_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ubicacion(ubicacion_id: int, session: AsyncSession = Depends(get_session)):
    ubicacion = await service.get_ubicacion(session, ubicacion_id)
    await service.delete_ubicacion(session, ubicacion)
