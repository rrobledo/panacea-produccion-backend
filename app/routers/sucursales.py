from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session
from app.schemas.sucursal import SucursalCreate, SucursalRead, SucursalUpdate
from app.services import sucursal_service as service

router = APIRouter(prefix="/sucursales", tags=["sucursales"])


@router.get("", response_model=list[SucursalRead])
async def list_sucursales(
    tipo: str | None = None,
    activa: bool | None = None,
    session: AsyncSession = Depends(get_session),
):
    sucursales = await service.list_sucursales(session, tipo=tipo, activa=activa)
    return [SucursalRead.from_orm_row(row) for row in sucursales]


@router.post("", response_model=SucursalRead, status_code=status.HTTP_201_CREATED)
async def create_sucursal(payload: SucursalCreate, session: AsyncSession = Depends(get_session)):
    sucursal = await service.create_sucursal(session, payload)
    return SucursalRead.from_orm_row(sucursal)


@router.put("/{sucursal_id}", response_model=SucursalRead)
async def update_sucursal(sucursal_id: int, payload: SucursalUpdate, session: AsyncSession = Depends(get_session)):
    sucursal = await service.get_sucursal(session, sucursal_id)
    sucursal = await service.update_sucursal(session, sucursal, payload)
    return SucursalRead.from_orm_row(sucursal)
